# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Baseline snapshots: persist a scan's token weights and detect drift.

A baseline pins each server's anthropic token total and a content hash per
tool (name + description + input schema). ``compare`` reports growth, new or
removed servers, and tool definition changes — the hash catches description
swaps that keep the token count identical (the v0.7 rug-pull pin).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mcp_checkup.models import ToolInfo
from mcp_checkup.scan import ScanReport

DEFAULT_BASELINE = ".mcp-checkup-baseline.json"

_BASELINE_SCHEMA_VERSION = 1


def _tool_hash(tool: ToolInfo) -> str:
    """Stable content hash of one tool definition (sha256 of compact JSON)."""
    doc = {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }
    blob = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def snapshot(report: ScanReport) -> dict:
    """Baseline document for *report*. Servers that errored are skipped."""
    servers: dict = {}
    for entry in report.entries:
        if not entry.result:
            continue
        result = entry.result
        servers[entry.discovered.spec.name] = {
            "total_anthropic": result.totals().get("anthropic", 0),
            "tools": {
                tw.tool.name: {
                    "tokens": tw.tokens.get("anthropic", 0),
                    "hash": _tool_hash(tw.tool),
                }
                for tw in result.tool_weights
            },
        }
    return {"schema_version": _BASELINE_SCHEMA_VERSION, "servers": servers}


def write(report: ScanReport, path: str | Path) -> None:
    """Write the baseline snapshot of *report* to *path*."""
    doc = json.dumps(snapshot(report), indent=2, sort_keys=True)
    Path(path).write_text(doc + "\n", encoding="utf-8")


def load(path: str | Path) -> dict | None:
    """Load a baseline document, or None when missing/corrupt."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("servers"), dict):
        return None
    return doc


def hash_changes(report: ScanReport, baseline: dict) -> list[tuple[str, str]]:
    """(server, tool) pairs whose definition hash differs from the baseline pin.

    A changed hash with unchanged-looking behavior is the rug-pull signature:
    the tool was approved once, then its description/schema changed underneath.
    """
    current = snapshot(report)["servers"]
    pinned = baseline.get("servers", {})
    out: list[tuple[str, str]] = []
    for server, data in current.items():
        base_tools = pinned.get(server, {}).get("tools", {})
        for tool, info in data["tools"].items():
            old = base_tools.get(tool)
            if old and old.get("hash") != info["hash"]:
                out.append((server, tool))
    return out


def compare(report: ScanReport, baseline: dict) -> list[str]:
    """Human-readable drift lines between *report* and *baseline*.

    Empty list means no changes.
    """
    current = snapshot(report)["servers"]
    base = baseline.get("servers", {})
    lines: list[str] = []
    for name in sorted(set(base) | set(current)):
        if name not in base:
            lines.append(f"new server '{name}' ({current[name]['total_anthropic']:,} tokens)")
            continue
        if name not in current:
            lines.append(
                f"removed server '{name}' (was {base[name].get('total_anthropic', 0):,} tokens)"
            )
            continue
        old_total = base[name].get("total_anthropic", 0)
        new_total = current[name]["total_anthropic"]
        if new_total != old_total:
            verb = "grew" if new_total > old_total else "shrank"
            lines.append(
                f"server '{name}' {verb} {new_total - old_total:+,} anthropic tokens "
                f"since baseline ({old_total:,} -> {new_total:,})"
            )
        base_tools = base[name].get("tools", {})
        for tool_name, tool in sorted(current[name]["tools"].items()):
            old_tool = base_tools.get(tool_name)
            if old_tool and old_tool.get("hash") != tool["hash"]:
                lines.append(f"tool '{tool_name}' on '{name}' changed since baseline")
    return lines
