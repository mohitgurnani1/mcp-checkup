# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Discovery contract: every client loader returns normalized Discovered entries.

Loaders must never raise on malformed/missing config files — return an empty
list (missing) or a Discovered with ``error`` set (unparsable/unresolvable), so
one broken client never breaks the scan.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp_checkup.models import ServerSpec, Transport


@dataclass
class Discovered:
    """One MCP server entry found in a client config."""

    spec: ServerSpec
    client: str  # e.g. "claude-desktop"
    source: str  # config file path it came from
    scope: str | None = None  # e.g. "project", "user", "local"
    error: str | None = None  # e.g. "needs-input" for unresolvable placeholders

    def identity(self) -> tuple:
        """Dedup key: same underlying server referenced from several clients."""
        s = self.spec
        if s.transport is Transport.HTTP:
            return ("http", s.url)
        return ("stdio", s.command, tuple(s.args))


def parse_servers_dict(
    servers: dict[str, Any], client: str, source: str, scope: str | None = None
) -> list[Discovered]:
    """Normalize an mcpServers-style mapping into Discovered entries."""
    out: list[Discovered] = []
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url") or entry.get("serverUrl")
        if url:
            spec = ServerSpec(
                name=name,
                transport=Transport.HTTP,
                url=url,
                headers=entry.get("headers") or {},
            )
        elif entry.get("command"):
            spec = ServerSpec(
                name=name,
                transport=Transport.STDIO,
                command=entry["command"],
                args=entry.get("args") or [],
                env=entry.get("env") or {},
            )
        else:
            continue
        error = None
        blob = f"{url or ''} {entry.get('command', '')} {' '.join(entry.get('args') or [])}"
        if "${input:" in blob:
            error = "needs-input"
        out.append(Discovered(spec=spec, client=client, source=source, scope=scope, error=error))
    return out


# Populated by the loader modules at import time via register().
CLIENTS: dict[str, Callable[[Path], list[Discovered]]] = {}


def register(name: str) -> Callable:
    def deco(fn: Callable[[Path], list[Discovered]]) -> Callable:
        CLIENTS[name] = fn
        return fn

    return deco


def discover_all(home: Path | None = None, clients: list[str] | None = None) -> list[Discovered]:
    """Run all (or selected) client loaders against ``home`` (default: user home)."""
    # Import loaders lazily so registration happens on first use.
    from mcp_checkup.discovery import (  # noqa: F401
        claude_code,
        claude_desktop,
        cursor,
        vscode,
        windsurf,
    )

    home = home or Path.home()
    found: list[Discovered] = []
    for name, loader in CLIENTS.items():
        if clients and name not in clients:
            continue
        found.extend(loader(home))
    return found
