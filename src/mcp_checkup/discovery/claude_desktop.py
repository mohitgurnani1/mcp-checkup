# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Claude Desktop config discovery (claude_desktop_config.json)."""

from __future__ import annotations

import json
import sys
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


def _config_path(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        return home / "AppData/Roaming/Claude/claude_desktop_config.json"
    return home / ".config/Claude/claude_desktop_config.json"


@register("claude-desktop")
def load(home: Path) -> list[Discovered]:
    path = _config_path(home)
    servers = _load_json(path).get("mcpServers")
    if not isinstance(servers, dict):
        return []
    return parse_servers_dict(servers, "claude-desktop", str(path), scope="user")
