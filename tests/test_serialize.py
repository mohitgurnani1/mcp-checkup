# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from mcp_checkup.models import PROVIDERS, ToolInfo
from mcp_checkup.serialize import serialize, to_anthropic, to_gemini, to_openai

TOOL = ToolInfo(
    name="get_weather",
    description="Get current weather for a city.",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
)


def test_anthropic_shape() -> None:
    doc = json.loads(to_anthropic(TOOL))
    assert list(doc) == ["name", "description", "input_schema"]
    assert doc["name"] == TOOL.name
    assert doc["description"] == TOOL.description
    assert doc["input_schema"] == TOOL.input_schema


def test_openai_shape() -> None:
    doc = json.loads(to_openai(TOOL))
    assert list(doc) == ["type", "function"]
    assert doc["type"] == "function"
    assert list(doc["function"]) == ["name", "description", "parameters"]
    assert doc["function"]["name"] == TOOL.name
    assert doc["function"]["description"] == TOOL.description
    assert doc["function"]["parameters"] == TOOL.input_schema


def test_gemini_shape() -> None:
    doc = json.loads(to_gemini(TOOL))
    assert list(doc) == ["name", "description", "parameters"]
    assert doc["name"] == TOOL.name
    assert doc["description"] == TOOL.description
    assert doc["parameters"] == TOOL.input_schema


@pytest.mark.parametrize("provider", PROVIDERS)
def test_compact_no_spaces_after_separators(provider: str) -> None:
    wire = serialize(TOOL, provider)
    assert ", " not in wire
    assert ": " not in wire
    # Round-trips to the same document as a non-compact dump would.
    assert json.loads(wire) == json.loads(json.dumps(json.loads(wire), indent=2))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_serialize_dispatch_matches_direct_functions(provider: str) -> None:
    direct = {"anthropic": to_anthropic, "openai": to_openai, "gemini": to_gemini}
    assert serialize(TOOL, provider) == direct[provider](TOOL)


def test_serialize_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        serialize(TOOL, "mistral")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_unicode_round_trip(provider: str) -> None:
    tool = ToolInfo(
        name="météo",
        description="Прогноз погоды 🌤️ 東京",
        input_schema={"type": "object", "properties": {"città": {"type": "string"}}},
    )
    doc = json.loads(serialize(tool, provider))
    inner = doc["function"] if provider == "openai" else doc
    assert inner["name"] == "météo"
    assert inner["description"] == "Прогноз погоды 🌤️ 東京"
    schema = inner["input_schema" if provider == "anthropic" else "parameters"]
    assert "città" in schema["properties"]
