# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""VS Code config discovery: workspace .vscode/mcp.json plus user-profile mcp.json.

VS Code uses a top-level ``servers`` key (not ``mcpServers``) and may reference
``${input:...}`` placeholders, which parse_servers_dict tags as needs-input.
"""

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


def _user_config_path(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library/Application Support/Code/User/mcp.json"
    if sys.platform == "win32":
        return home / "AppData/Roaming/Code/User/mcp.json"
    return home / ".config/Code/User/mcp.json"


@register("vscode")
def load(home: Path) -> list[Discovered]:
    out: list[Discovered] = []
    for path, scope in (
        (Path.cwd() / ".vscode/mcp.json", "project"),
        (_user_config_path(home), "user"),
    ):
        servers = _load_json(path).get("servers")
        if isinstance(servers, dict):
            out.extend(parse_servers_dict(servers, "vscode", str(path), scope=scope))
    return out
