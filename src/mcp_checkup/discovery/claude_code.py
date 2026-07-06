# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Claude Code config discovery: project .mcp.json plus ~/.claude.json scopes."""

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


@register("claude-code")
def load(home: Path) -> list[Discovered]:
    out: list[Discovered] = []
    cwd = Path.cwd()

    # Project scope: .mcp.json checked into the current project.
    project_path = cwd / ".mcp.json"
    servers = _load_json(project_path).get("mcpServers")
    if isinstance(servers, dict):
        out.extend(parse_servers_dict(servers, "claude-code", str(project_path), scope="project"))

    # User + local scopes both live in ~/.claude.json.
    user_path = home / ".claude.json"
    data = _load_json(user_path)

    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        out.extend(parse_servers_dict(servers, "claude-code", str(user_path), scope="user"))

    # Local scope: per-project entries keyed by absolute project path.
    projects = data.get("projects")
    if isinstance(projects, dict):
        project_entry = projects.get(str(cwd))
        if isinstance(project_entry, dict):
            servers = project_entry.get("mcpServers")
            if isinstance(servers, dict):
                out.extend(
                    parse_servers_dict(servers, "claude-code", str(user_path), scope="local")
                )

    return out
