# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Diff two baseline snapshots and render the drift.

Both inputs are baseline documents shaped like
:func:`mcp_checkup.baseline.snapshot`. Unlike :func:`mcp_checkup.baseline.compare`
(which diffs a live scan against one baseline), this compares two saved
baselines — useful for "what changed between last week and today".

Coloring in :func:`render_diff` is deliberately inverted relative to a
conventional diff: *less* context tax is good. Growth and new surface
(``grew``/``new``) render red, definition changes render yellow, and
``shrank``/``removed`` render green.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text


def diff_baselines(old: dict, new: dict) -> list[str]:
    """Human-readable drift lines from *old* to *new* baseline documents.

    Reports per-server anthropic token deltas, added/removed servers,
    added/removed tools, and tools whose definition hash changed. Ordering is
    deterministic (servers sorted by name, then tools sorted by name).
    Returns an empty list when the two baselines are identical.
    """
    old_servers = old.get("servers", {})
    new_servers = new.get("servers", {})
    lines: list[str] = []
    for name in sorted(set(old_servers) | set(new_servers)):
        if name not in old_servers:
            total = new_servers[name].get("total_anthropic", 0)
            lines.append(f"new server '{name}' ({total:,} tokens)")
            continue
        if name not in new_servers:
            total = old_servers[name].get("total_anthropic", 0)
            lines.append(f"removed server '{name}' (was {total:,} tokens)")
            continue
        old_total = old_servers[name].get("total_anthropic", 0)
        new_total = new_servers[name].get("total_anthropic", 0)
        if new_total != old_total:
            verb = "grew" if new_total > old_total else "shrank"
            lines.append(
                f"server '{name}' {verb} {new_total - old_total:+,} anthropic tokens "
                f"({old_total:,} -> {new_total:,})"
            )
        old_tools = old_servers[name].get("tools", {})
        new_tools = new_servers[name].get("tools", {})
        for tool in sorted(set(old_tools) | set(new_tools)):
            if tool not in old_tools:
                tokens = new_tools[tool].get("tokens", 0)
                lines.append(f"new tool '{tool}' on '{name}' ({tokens:,} tokens)")
            elif tool not in new_tools:
                lines.append(f"removed tool '{tool}' on '{name}'")
            elif old_tools[tool].get("hash") != new_tools[tool].get("hash"):
                lines.append(f"tool '{tool}' on '{name}' definition changed")
    return lines


def _style(line: str) -> str:
    """Inverted diff coloring: growth is bad (red), reduction is good (green)."""
    if line.startswith(("new server", "new tool")) or " grew " in line:
        return "red"
    if line.startswith("removed") or " shrank " in line:
        return "green"
    return "yellow"  # definition changed


def render_diff(lines: list[str], console: Console | None = None) -> None:
    """Print drift lines from :func:`diff_baselines`, one styled line each."""
    console = console or Console()
    for line in lines:
        console.print(Text(line, style=_style(line)))
