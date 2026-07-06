# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Serialize a ToolInfo into each provider's tool-definition wire format.

Each function returns the compact JSON string a tool definition occupies on
the wire when sent to that provider, which is what token counting is based on.
"""

from __future__ import annotations

import json

from mcp_checkup.models import PROVIDERS, ToolInfo


def to_anthropic(tool: ToolInfo) -> str:
    """Anthropic Messages API tool definition (one entry of ``tools``)."""
    return json.dumps(
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def to_openai(tool: ToolInfo) -> str:
    """OpenAI Chat Completions function-tool definition (one entry of ``tools``)."""
    return json.dumps(
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def to_gemini(tool: ToolInfo) -> str:
    """Gemini function declaration (one ``functionDeclarations`` entry)."""
    return json.dumps(
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


_SERIALIZERS = {
    "anthropic": to_anthropic,
    "openai": to_openai,
    "gemini": to_gemini,
}

# _SERIALIZERS must cover exactly the providers declared in models.PROVIDERS.
assert set(_SERIALIZERS) == set(PROVIDERS)


def serialize(tool: ToolInfo, provider: str) -> str:
    """Serialize *tool* into *provider*'s wire format.

    *provider* must be one of :data:`mcp_checkup.models.PROVIDERS`.
    """
    try:
        return _SERIALIZERS[provider](tool)
    except KeyError:
        raise ValueError(f"unknown provider {provider!r}; expected one of {PROVIDERS}") from None
