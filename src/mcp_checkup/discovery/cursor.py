# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Cursor config discovery: global ~/.cursor/mcp.json plus project .cursor/mcp.json."""

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


@register("cursor")
def load(home: Path) -> list[Discovered]:
    out: list[Discovered] = []
    for path, scope in (
        (home / ".cursor/mcp.json", "user"),
        (Path.cwd() / ".cursor/mcp.json", "project"),
    ):
        servers = _load_json(path).get("mcpServers")
        if isinstance(servers, dict):
            out.extend(parse_servers_dict(servers, "cursor", str(path), scope=scope))
    return out
