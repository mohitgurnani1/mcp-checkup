# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Windsurf config discovery (~/.codeium/windsurf/mcp_config.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp_checkup.discovery.base import Discovered, parse_servers_dict, register


def _load_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from ``path``; missing or malformed files yield {}."""
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@register("windsurf")
def load(home: Path) -> list[Discovered]:
    path = home / ".codeium/windsurf/mcp_config.json"
    servers = _load_json(path).get("mcpServers")
    if not isinstance(servers, dict):
        return []
    return parse_servers_dict(servers, "windsurf", str(path), scope="user")
