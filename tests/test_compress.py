# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Tests for schema compression (compress.py).

Covers purity, the semantic-safety guarantee (type/properties/required/items
never change), description policies, anyOf/oneOf const collapse, oversized
enum dropping, token savings, and jsonschema cross-validation that instances
valid under the original schema stay valid under the compressed one.
"""

import copy
from typing import Any

import jsonschema
import pytest

from mcp_checkup.compress import CompressPolicy, compress_schema, compress_tool, savings
from mcp_checkup.models import ToolInfo

LONG_PROSE = (
    "Search the corpus for matching documents. The pipeline tokenizes the query with a "
    "locale-aware analyzer, matches against a positional inverted index, blends BM25 with "
    "a dense-vector component, and re-ranks candidates with a cascade nobody remembers "
    "tuning. Results can be filtered, grouped, deduplicated, and paginated with a stable "
    "cursor. In short: it searches things."
)

BLOATED_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Search input",
    "$comment": "internal note",
    "deprecated": False,
    "type": "object",
    "description": LONG_PROSE,
    "properties": {
        "query": {
            "type": "string",
            "description": "The free-text query to run. Long queries are truncated.",
            "examples": ["hello", "title:foo"],
            "default": "",
        },
        "mode": {
            "description": "Ranking mode. Ignored when the corpus is empty.",
            "anyOf": [
                {"const": "fast", "type": "string"},
                {"const": "slow", "type": "string"},
            ],
        },
        "region": {
            "type": "string",
            "description": "Region code. Determines the shard set queried.",
            "enum": [f"region-{i:02d}" for i in range(25)],
        },
        "filters": {
            "type": "object",
            "title": "Filters",
            "description": "Structured predicates applied before ranking.",
            "properties": {
                "tags": {
                    "type": "array",
                    "description": "Tags every hit must carry. Order is irrelevant.",
                    "items": {"type": "string", "description": "One tag.", "title": "Tag"},
                },
            },
            "required": ["tags"],
        },
    },
    "required": ["query"],
}

LEAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
    "required": ["a", "b"],
}

BLOATED_INSTANCE = {
    "query": "hello",
    "mode": "fast",
    # Deliberately beyond the first max_enum entries of the original enum.
    "region": "region-20",
    "filters": {"tags": ["a", "b"]},
}


def _bloated_tool() -> ToolInfo:
    return ToolInfo(name="search", description=LONG_PROSE, input_schema=BLOATED_SCHEMA)


def _lean_tool() -> ToolInfo:
    return ToolInfo(name="add", description="Add two integers.", input_schema=LEAN_SCHEMA)


def _structure(node: Any) -> Any:
    """The parts compression guarantees to preserve: type/properties/required/items."""
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    if "type" in node:
        out["type"] = node["type"]
    if "required" in node:
        out["required"] = node["required"]
    if "properties" in node:
        out["properties"] = {k: _structure(v) for k, v in node["properties"].items()}
    if "items" in node:
        items = node["items"]
        out["items"] = (
            [_structure(i) for i in items] if isinstance(items, list) else _structure(items)
        )
    return out


def _all_descriptions(node: Any) -> list[str]:
    """Every description string in *node*, skipping properties named 'description'."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                found.append(value)
            elif key in ("properties", "patternProperties", "$defs", "definitions"):
                for sub in value.values():
                    found.extend(_all_descriptions(sub))
            else:
                found.extend(_all_descriptions(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_all_descriptions(item))
    return found


# --- purity ------------------------------------------------------------------


@pytest.mark.parametrize("descriptions", ["none", "first-sentence", "full"])
def test_compress_schema_is_pure(descriptions):
    original = copy.deepcopy(BLOATED_SCHEMA)
    compress_schema(BLOATED_SCHEMA, CompressPolicy(descriptions=descriptions))
    assert original == BLOATED_SCHEMA


def test_compress_tool_does_not_mutate_input_tool():
    tool = _bloated_tool()
    schema_snapshot = copy.deepcopy(tool.input_schema)
    description_snapshot = tool.description
    compress_tool(tool, CompressPolicy())
    assert tool.input_schema == schema_snapshot
    assert tool.description == description_snapshot


# --- semantic-safety guarantee ------------------------------------------------


@pytest.mark.parametrize("descriptions", ["none", "first-sentence", "full"])
def test_guarantee_type_properties_required_items_unchanged(descriptions):
    policy = CompressPolicy(descriptions=descriptions)
    compressed = compress_schema(BLOATED_SCHEMA, policy)
    assert _structure(compressed) == _structure(BLOATED_SCHEMA)


def test_property_named_like_stripped_keyword_is_preserved():
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "default": {"type": "boolean"},
        },
        "required": ["title"],
    }
    compressed = compress_schema(schema, CompressPolicy(descriptions="none"))
    assert set(compressed["properties"]) == {"title", "description", "default"}
    assert compressed["required"] == ["title"]


# --- description policies -----------------------------------------------------


def test_descriptions_none_drops_all_descriptions():
    compressed = compress_schema(BLOATED_SCHEMA, CompressPolicy(descriptions="none"))
    assert _all_descriptions(compressed) == []


def test_descriptions_first_sentence_keeps_first_sentence():
    compressed = compress_schema(BLOATED_SCHEMA, CompressPolicy(descriptions="first-sentence"))
    query = compressed["properties"]["query"]
    assert query["description"] == "The free-text query to run."
    assert compressed["description"] == "Search the corpus for matching documents."


def test_descriptions_first_sentence_caps_at_120_chars():
    one_long_sentence = "word " * 60  # no period, 300 chars
    schema = {"type": "string", "description": one_long_sentence}
    compressed = compress_schema(schema, CompressPolicy(descriptions="first-sentence"))
    assert len(compressed["description"]) <= 120


def test_descriptions_full_keeps_descriptions_verbatim():
    schema = {
        "type": "object",
        "properties": {"q": {"type": "string", "description": LONG_PROSE}},
    }
    compressed = compress_schema(schema, CompressPolicy(descriptions="full"))
    assert compressed["properties"]["q"]["description"] == LONG_PROSE


def test_unknown_descriptions_policy_raises():
    with pytest.raises(ValueError):
        compress_schema({"type": "object"}, CompressPolicy(descriptions="bogus"))


# --- anyOf/oneOf const collapse ------------------------------------------------


def test_anyof_consts_collapse_to_enum_without_adding_type():
    compressed = compress_schema(BLOATED_SCHEMA, CompressPolicy(descriptions="none"))
    mode = compressed["properties"]["mode"]
    assert "anyOf" not in mode
    assert mode["enum"] == ["fast", "slow"]
    # The enum alone is equivalent to the union; no "type" is invented.
    assert "type" not in mode


def test_oneof_bare_consts_collapse_to_enum():
    schema = {"oneOf": [{"const": 1}, {"const": 2}, {"const": 3}]}
    compressed = compress_schema(schema, CompressPolicy())
    assert compressed == {"enum": [1, 2, 3]}


def test_anyof_with_non_const_members_is_left_alone():
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    compressed = compress_schema(schema, CompressPolicy())
    assert compressed == schema


def test_anyof_consts_with_differing_types_is_left_alone():
    schema = {"anyOf": [{"const": "a", "type": "string"}, {"const": 1, "type": "integer"}]}
    compressed = compress_schema(schema, CompressPolicy())
    assert compressed == schema


def test_empty_anyof_is_left_alone():
    schema = {"anyOf": []}
    compressed = compress_schema(schema, CompressPolicy())
    assert compressed == schema


def test_anyof_const_members_with_extra_keys_are_not_collapsed():
    # A member carrying more than const/type may constrain further; do not collapse.
    schema = {"anyOf": [{"const": "a", "description": "The letter a."}, {"const": "b"}]}
    compressed = compress_schema(schema, CompressPolicy(descriptions="full"))
    assert compressed == schema


# --- oversized enums ------------------------------------------------------------


def test_oversized_enum_dropped_keeping_base_type():
    compressed = compress_schema(BLOATED_SCHEMA, CompressPolicy(descriptions="none"))
    region = compressed["properties"]["region"]
    assert "enum" not in region
    assert region["type"] == "string"
    assert "description" not in region  # policy "none": no note either


def test_oversized_enum_note_appended_when_descriptions_kept():
    compressed = compress_schema(BLOATED_SCHEMA, CompressPolicy(descriptions="first-sentence"))
    region = compressed["properties"]["region"]
    assert "enum" not in region
    # 25 values, max_enum 10 -> 15 more; note appended after the kept sentence.
    assert region["description"].startswith("Region code.")
    assert "(+15 more values accepted)" in region["description"]


def test_enum_at_max_enum_is_kept():
    schema = {"type": "string", "enum": [f"v{i}" for i in range(10)]}
    compressed = compress_schema(schema, CompressPolicy())
    assert compressed["enum"] == schema["enum"]


def test_collapsed_const_union_still_subject_to_max_enum():
    schema = {"anyOf": [{"const": f"v{i}", "type": "string"} for i in range(12)]}
    compressed = compress_schema(schema, CompressPolicy(descriptions="none"))
    assert "anyOf" not in compressed
    assert "enum" not in compressed
    assert compressed["type"] == "string"


# --- compress_tool ---------------------------------------------------------------


def test_compress_tool_description_none_yields_empty_string():
    tool = compress_tool(_bloated_tool(), CompressPolicy(descriptions="none"))
    assert tool.description == ""
    assert tool.name == "search"


def test_compress_tool_description_first_sentence():
    tool = compress_tool(_bloated_tool(), CompressPolicy(descriptions="first-sentence"))
    assert tool.description == "Search the corpus for matching documents."


# --- savings ----------------------------------------------------------------------


def test_savings_positive_on_bloated_tool():
    before, after = savings(_bloated_tool(), CompressPolicy())
    assert before > after
    assert after > 0


def test_savings_zero_on_lean_tool():
    before, after = savings(_lean_tool(), CompressPolicy())
    assert before == after


# --- jsonschema cross-validation ----------------------------------------------------

CROSS_VALIDATION_CASES = [
    (BLOATED_SCHEMA, BLOATED_INSTANCE),
    (
        {
            "type": "object",
            "properties": {
                "level": {
                    "title": "Level",
                    "anyOf": [{"const": "debug"}, {"const": "info"}, {"const": "error"}],
                },
            },
            "required": ["level"],
        },
        {"level": "info"},
    ),
    (
        {
            "type": "array",
            "description": "A list of points. Each point is x/y with an oversized unit enum.",
            "items": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "default": 0},
                    "y": {"type": "number", "examples": [1.5]},
                    "unit": {"type": "string", "enum": [f"unit-{i}" for i in range(30)]},
                },
                "required": ["x", "y"],
            },
        },
        [{"x": 1.0, "y": 2.0, "unit": "unit-29"}, {"x": 0.0, "y": 0.0}],
    ),
]


@pytest.mark.parametrize("schema,instance", CROSS_VALIDATION_CASES)
@pytest.mark.parametrize("descriptions", ["none", "first-sentence", "full"])
def test_instance_valid_under_original_stays_valid_under_compressed(schema, instance, descriptions):
    jsonschema.validate(instance, schema)  # sanity: valid under the original
    compressed = compress_schema(schema, CompressPolicy(descriptions=descriptions))
    jsonschema.validate(instance, compressed)  # must not be rejected after compression
