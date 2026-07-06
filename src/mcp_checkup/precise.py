# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Optional precise token counting via Anthropic's count_tokens API.

Everything else in mcp-checkup estimates with tiktoken; this module asks
Anthropic's tokenizer for the real input-token count of a tool set. It is
strictly opt-in: it needs the ``precise`` extra (``pip install
mcp-checkup[precise]``) and an ``ANTHROPIC_API_KEY``, and degrades to
``None`` when either is missing.
"""

from __future__ import annotations

import os

from mcp_checkup.models import ToolInfo


def count_precise(tools: list[ToolInfo], model: str) -> int | None:
    """Exact Anthropic input-token count for *tools* on *model*.

    Returns ``None`` when the ``anthropic`` package is not installed or
    ``ANTHROPIC_API_KEY`` is not set. The count includes a minimal one-word
    user message ("hi"), required by the API.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic()
    response = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ],
    )
    return response.input_tokens
