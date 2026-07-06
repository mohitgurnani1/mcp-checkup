# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Token-weight estimation for MCP server inventories.

All counts here are *estimates*: text is tokenized with tiktoken's
``o200k_base`` encoding, which is exact for OpenAI's GPT-4o family and a
reasonable proxy for Anthropic and Gemini models (their tokenizers are not
public, but BPE vocabularies of this size land in the same ballpark).
"""

from __future__ import annotations

import functools
import json

import tiktoken

from mcp_checkup.models import (
    PROVIDERS,
    ServerInventory,
    ToolInfo,
    ToolWeight,
    WeighResult,
)
from mcp_checkup.serialize import serialize

# Anthropic's documented tool-use system prompt overhead for Claude
# Sonnet-class models with `auto` tool choice (see
# https://docs.anthropic.com/en/docs/build-with-claude/tool-use — values
# range ~159-530 by model/choice; 346 is the documented Sonnet auto value).
ANTHROPIC_TOOL_SYSTEM_OVERHEAD = 346


@functools.lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """Cached o200k_base encoding (first call downloads the BPE file)."""
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    """Estimated token count of *text* under the o200k_base encoding.

    Exact for OpenAI GPT-4o-family models; a proxy estimate for
    Anthropic and Gemini models.
    """
    return len(_encoding().encode(text))


def system_overhead(provider: str) -> int:
    """Fixed system-prompt token overhead a provider adds when tools are present.

    Returns :data:`ANTHROPIC_TOOL_SYSTEM_OVERHEAD` for ``"anthropic"`` and 0
    for other providers, where the overhead is unknown/undocumented.
    """
    if provider == "anthropic":
        return ANTHROPIC_TOOL_SYSTEM_OVERHEAD
    return 0


def weigh_tool(tool: ToolInfo) -> ToolWeight:
    """Estimated token cost of *tool*'s definition in each provider's wire format."""
    return ToolWeight(
        tool=tool,
        tokens={provider: count_tokens(serialize(tool, provider)) for provider in PROVIDERS},
    )


def weigh_inventory(inv: ServerInventory) -> WeighResult:
    """Estimated token weight of everything *inv* advertises, per provider.

    Tool definitions are serialized into each provider's actual wire format
    before counting. Resources and prompts have no provider-specific wire
    format, so they are counted once from a compact JSON list of their
    metadata dicts and the same provider-agnostic estimate is reported for
    every provider.
    """
    resources_json = json.dumps(
        [{"uri": r.uri, "name": r.name, "description": r.description} for r in inv.resources],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    prompts_json = json.dumps(
        [{"name": p.name, "description": p.description} for p in inv.prompts],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    resource_count = count_tokens(resources_json)
    prompt_count = count_tokens(prompts_json)
    return WeighResult(
        inventory=inv,
        tool_weights=[weigh_tool(tool) for tool in inv.tools],
        resource_tokens=dict.fromkeys(PROVIDERS, resource_count),
        prompt_tokens=dict.fromkeys(PROVIDERS, prompt_count),
    )
