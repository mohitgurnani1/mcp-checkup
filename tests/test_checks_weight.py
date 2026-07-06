# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the weight checks (W01-W05).

Check functions are invoked directly through the CHECKS registry after
importing ``mcp_checkup.checks.weight`` — ``run_checks`` is deliberately
not used here because it also imports the security check module.
"""

import copy

import mcp_checkup.checks.weight as weight  # importing registers W01-W05
from mcp_checkup.checks.base import CHECKS, CheckContext, Severity
from mcp_checkup.models import ServerInventory, ServerSpec, ToolInfo, Transport
from mcp_checkup.serialize import serialize
from mcp_checkup.tokens import count_tokens


def _inv(name: str, tools: list[ToolInfo]) -> ServerInventory:
    return ServerInventory(
        spec=ServerSpec(name=name, transport=Transport.STDIO, command=name),
        tools=tools,
    )


def _ctx(inv: ServerInventory, all_invs: list[ServerInventory] | None = None) -> CheckContext:
    return CheckContext(inventory=inv, all_inventories=all_invs if all_invs is not None else [inv])


def _run(check_id: str, ctx: CheckContext):
    return CHECKS[check_id].fn(ctx)


LONG_PROSE = " ".join(
    f"This parameter controls aspect number {i} of the operation in exhaustive detail, "
    "including edge cases, retries, pagination, and formatting quirks."
    for i in range(20)
)

BLOATED_TOOL = ToolInfo(
    name="mega_search",
    description="Search things.",
    input_schema={
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "title": "Mega search input",
        "$comment": "internal note",
        "properties": {
            "query": {"type": "string", "description": LONG_PROSE, "examples": ["a", "b"]},
            "scope": {"type": "string", "description": LONG_PROSE, "default": "all"},
            "region": {
                "type": "string",
                "description": LONG_PROSE,
                "enum": [f"region-{i:03d}-with-a-fairly-long-identifier" for i in range(30)],
            },
        },
        "required": ["query"],
    },
)

LEAN_TOOL = ToolInfo(
    name="get_weather",
    description="Get current weather for a city.",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
)


# --- minimal_schema ---------------------------------------------------------


def test_minimal_schema_strips_doc_keys_and_big_enums() -> None:
    minimal = weight.minimal_schema(BLOATED_TOOL.input_schema)
    assert "$schema" not in minimal
    assert "title" not in minimal
    assert "$comment" not in minimal
    props = minimal["properties"]
    for prop in props.values():
        assert "description" not in prop
        assert "examples" not in prop
        assert "default" not in prop
    # 30-entry enum dropped, but the property and its type survive.
    assert "enum" not in props["region"]
    assert props["region"]["type"] == "string"
    # Structure keys preserved.
    assert minimal["type"] == "object"
    assert minimal["required"] == ["query"]
    assert set(props) == {"query", "scope", "region"}


def test_minimal_schema_keeps_small_enums_and_items() -> None:
    schema = {
        "type": "object",
        "properties": {
            "unit": {"type": "string", "enum": ["c", "f"], "description": "unit"},
            "tags": {"type": "array", "items": {"type": "string", "title": "tag"}},
        },
    }
    minimal = weight.minimal_schema(schema)
    assert minimal["properties"]["unit"]["enum"] == ["c", "f"]
    assert minimal["properties"]["tags"]["items"] == {"type": "string"}


def test_minimal_schema_is_pure() -> None:
    schema = copy.deepcopy(BLOATED_TOOL.input_schema)
    snapshot = copy.deepcopy(schema)
    out = weight.minimal_schema(schema)
    assert schema == snapshot  # input unmutated
    assert out is not schema
    assert out != schema


# --- W01 schema bloat -------------------------------------------------------


def test_w01_flags_bloated_tool() -> None:
    findings = _run("W01", _ctx(_inv("srv", [BLOATED_TOOL])))
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "W01"
    assert f.severity is Severity.MEDIUM
    assert f.server == "srv"
    assert f.tool == "mega_search"
    assert "'mega_search' is " in f.summary
    assert "x its minimal schema (" in f.summary
    assert "tokens)" in f.summary


def test_w01_ignores_lean_tool() -> None:
    assert _run("W01", _ctx(_inv("srv", [LEAN_TOOL]))) == []


def test_w01_ignores_large_but_dense_tool() -> None:
    # Large (> 300 tokens) but nothing to strip: minimal ~= actual, ratio ~1.
    dense = ToolInfo(
        name="dense",
        description="Dense tool.",
        input_schema={
            "type": "object",
            "properties": {f"field_number_{i}": {"type": "string"} for i in range(120)},
        },
    )
    assert count_tokens(serialize(dense, "anthropic")) > weight.BLOAT_MIN_ACTUAL_TOKENS
    assert _run("W01", _ctx(_inv("srv", [dense]))) == []


# --- W02 oversized description ----------------------------------------------


def test_w02_flags_huge_description() -> None:
    tool = ToolInfo(
        name="chatty",
        description="usage note protocol detail " * 300,  # ~1200 tokens
        input_schema={"type": "object", "properties": {}},
    )
    findings = _run("W02", _ctx(_inv("srv", [tool])))
    assert len(findings) == 1
    assert findings[0].check_id == "W02"
    assert findings[0].tool == "chatty"
    assert findings[0].severity is Severity.LOW


def test_w02_ignores_normal_description() -> None:
    assert _run("W02", _ctx(_inv("srv", [LEAN_TOOL]))) == []


# --- W03 enum explosion -----------------------------------------------------


def test_w03_flags_giant_enum_with_property_path() -> None:
    tool = ToolInfo(
        name="pick_country",
        description="Pick a country.",
        input_schema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "enum": [f"country-{i}" for i in range(51)]},
            },
        },
    )
    findings = _run("W03", _ctx(_inv("srv", [tool])))
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "W03"
    assert f.tool == "pick_country"
    assert "properties.country" in f.summary
    assert "51" in f.summary


def test_w03_ignores_enum_at_threshold() -> None:
    tool = ToolInfo(
        name="pick_country",
        description="Pick a country.",
        input_schema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "enum": [f"country-{i}" for i in range(50)]},
            },
        },
    )
    assert _run("W03", _ctx(_inv("srv", [tool]))) == []


# --- W04 tool count ---------------------------------------------------------


def _n_tools(n: int) -> list[ToolInfo]:
    return [
        ToolInfo(name=f"tool_{i}", description="d", input_schema={"type": "object"})
        for i in range(n)
    ]


def test_w04_flags_more_than_30_tools() -> None:
    findings = _run("W04", _ctx(_inv("big", _n_tools(31))))
    assert len(findings) == 1
    assert findings[0].check_id == "W04"
    assert findings[0].tool is None
    assert findings[0].summary == "server exposes 31 tools; models degrade with large tool lists"


def test_w04_ignores_exactly_30_tools() -> None:
    assert _run("W04", _ctx(_inv("ok", _n_tools(30)))) == []


# --- W05 duplicate tool names -----------------------------------------------


def _dup_tool() -> ToolInfo:
    return ToolInfo(name="search", description="Search.", input_schema={"type": "object"})


def test_w05_emits_one_finding_on_first_server_only() -> None:
    invs = [
        _inv("alpha", [_dup_tool()]),
        _inv("beta", [_dup_tool()]),
        _inv("gamma", [_dup_tool()]),
    ]
    per_server = {inv.spec.name: _run("W05", _ctx(inv, invs)) for inv in invs}
    assert len(per_server["alpha"]) == 1
    assert per_server["beta"] == []
    assert per_server["gamma"] == []
    f = per_server["alpha"][0]
    assert f.check_id == "W05"
    assert f.server == "alpha"
    assert f.tool == "search"
    assert "3 servers" in f.summary
    for name in ("alpha", "beta", "gamma"):
        assert name in f.summary


def test_w05_ignores_unique_names() -> None:
    invs = [
        _inv("alpha", [ToolInfo(name="a", description="", input_schema={})]),
        _inv("beta", [ToolInfo(name="b", description="", input_schema={})]),
    ]
    for inv in invs:
        assert _run("W05", _ctx(inv, invs)) == []


# --- registry ----------------------------------------------------------------


def test_all_weight_checks_registered_with_expected_severity() -> None:
    expected = {
        "W01": Severity.MEDIUM,
        "W02": Severity.LOW,
        "W03": Severity.LOW,
        "W04": Severity.LOW,
        "W05": Severity.LOW,
    }
    for check_id, severity in expected.items():
        assert check_id in CHECKS
        assert CHECKS[check_id].severity is severity
