# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Shared data model. Every other module codes against these types only."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

REPORT_SCHEMA_VERSION = 1


class Transport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"


@dataclass
class ServerSpec:
    """A single MCP server to inspect, normalized from any source."""

    name: str
    transport: Transport
    # stdio
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # http
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ResourceInfo:
    uri: str
    name: str
    description: str


@dataclass
class PromptInfo:
    name: str
    description: str


@dataclass
class ServerInventory:
    """Everything a server advertises during one session."""

    spec: ServerSpec
    tools: list[ToolInfo] = field(default_factory=list)
    resources: list[ResourceInfo] = field(default_factory=list)
    prompts: list[PromptInfo] = field(default_factory=list)


@dataclass
class ToolWeight:
    """Token estimates for one tool, per provider wire format."""

    tool: ToolInfo
    tokens: dict[str, int]  # provider name -> token estimate


@dataclass
class WeighResult:
    """Full weigh report for one server."""

    inventory: ServerInventory
    tool_weights: list[ToolWeight] = field(default_factory=list)
    resource_tokens: dict[str, int] = field(default_factory=dict)  # provider -> total
    prompt_tokens: dict[str, int] = field(default_factory=dict)  # provider -> total

    def totals(self) -> dict[str, int]:
        """Total tool-definition tokens per provider (excludes resources/prompts)."""
        out: dict[str, int] = {}
        for tw in self.tool_weights:
            for provider, n in tw.tokens.items():
                out[provider] = out.get(provider, 0) + n
        return out


PROVIDERS = ("anthropic", "openai", "gemini")
