# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

from mcp_checkup.models import (
    PROVIDERS,
    PromptInfo,
    ResourceInfo,
    ServerInventory,
    ServerSpec,
    ToolInfo,
    Transport,
)
from mcp_checkup.tokens import (
    ANTHROPIC_TOOL_SYSTEM_OVERHEAD,
    count_tokens,
    system_overhead,
    weigh_inventory,
    weigh_tool,
)

TOOL = ToolInfo(
    name="get_weather",
    description="Get current weather for a city.",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
)

# Golden values measured with tiktoken o200k_base (tiktoken 0.13.0).
GOLDEN_DESCRIPTION_TOKENS = 7
GOLDEN_TOOL_TOKENS = {"anthropic": 41, "openai": 47, "gemini": 40}


def test_count_tokens_golden_and_deterministic() -> None:
    assert count_tokens(TOOL.description) == GOLDEN_DESCRIPTION_TOKENS
    assert count_tokens(TOOL.description) == count_tokens(TOOL.description)
    assert count_tokens("") == 0


def test_weigh_tool_golden_per_provider() -> None:
    weight = weigh_tool(TOOL)
    assert weight.tool is TOOL
    assert weight.tokens == GOLDEN_TOOL_TOKENS


def test_provider_counts_differ_where_formats_differ() -> None:
    tokens = weigh_tool(TOOL).tokens
    assert set(tokens) == set(PROVIDERS)
    assert all(n > 0 for n in tokens.values())
    # OpenAI wraps the schema in {"type": "function", "function": {...}} so it
    # must cost more than the flatter Anthropic and Gemini formats.
    assert tokens["openai"] > tokens["anthropic"]
    assert tokens["openai"] > tokens["gemini"]
    # Anthropic and Gemini differ only by the input_schema/parameters key.
    assert tokens["anthropic"] != tokens["gemini"]


def test_system_overhead() -> None:
    assert system_overhead("anthropic") == ANTHROPIC_TOOL_SYSTEM_OVERHEAD == 346
    assert system_overhead("openai") == 0
    assert system_overhead("gemini") == 0
    assert system_overhead("unknown") == 0


def _inventory() -> ServerInventory:
    other_tool = ToolInfo(
        name="get_forecast",
        description="Get a 5-day forecast for a city.",
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    return ServerInventory(
        spec=ServerSpec(name="weather", transport=Transport.STDIO, command="weather-server"),
        tools=[TOOL, other_tool],
        resources=[ResourceInfo(uri="file:///cities.csv", name="cities", description="City list")],
        prompts=[PromptInfo(name="summarize", description="Summarize a weather report")],
    )


def test_weigh_inventory_totals_aggregation() -> None:
    result = weigh_inventory(_inventory())
    assert len(result.tool_weights) == 2
    totals = result.totals()
    assert set(totals) == set(PROVIDERS)
    for provider in PROVIDERS:
        expected = sum(tw.tokens[provider] for tw in result.tool_weights)
        assert totals[provider] == expected
        assert totals[provider] > GOLDEN_TOOL_TOKENS[provider]  # two tools > one
    assert (
        totals["anthropic"]
        == GOLDEN_TOOL_TOKENS["anthropic"] + result.tool_weights[1].tokens["anthropic"]
    )


def test_weigh_inventory_resource_and_prompt_tokens_provider_agnostic() -> None:
    result = weigh_inventory(_inventory())
    assert set(result.resource_tokens) == set(PROVIDERS)
    assert set(result.prompt_tokens) == set(PROVIDERS)
    # Resources/prompts have no provider-specific wire format: same estimate everywhere.
    assert len(set(result.resource_tokens.values())) == 1
    assert len(set(result.prompt_tokens.values())) == 1
    assert result.resource_tokens["openai"] > 0
    assert result.prompt_tokens["openai"] > 0


def test_weigh_inventory_empty_resources_and_prompts() -> None:
    inv = ServerInventory(spec=ServerSpec(name="bare", transport=Transport.HTTP, url="http://x"))
    result = weigh_inventory(inv)
    assert result.tool_weights == []
    assert result.totals() == {}
    # "[]" still costs a token or two, but must be uniform across providers.
    assert len(set(result.resource_tokens.values())) == 1
    assert len(set(result.prompt_tokens.values())) == 1
