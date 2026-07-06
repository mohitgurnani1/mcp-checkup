# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Shields.io endpoint badge for a scan's anthropic context tax.

The document follows the shields.io *endpoint badge* schema, so a hosted copy
(e.g. committed to a repo and served raw) can back a README badge that tracks
how many tokens the MCP setup costs before the first message.
"""

from __future__ import annotations

import json
from pathlib import Path

# (upper bound, color) — anthropic tool-definition tokens below the bound.
_THRESHOLDS = ((5_000, "green"), (20_000, "yellow"), (40_000, "orange"))


def badge_color(tokens: int) -> str:
    """Badge color for an anthropic token total: green < 5k, yellow < 20k,
    orange < 40k, red otherwise."""
    for bound, color in _THRESHOLDS:
        if tokens < bound:
            return color
    return "red"


def badge_doc(report) -> dict:
    """Shields.io endpoint-badge document for *report* (a ScanReport)."""
    tokens = report.totals().get("anthropic", 0)
    return {
        "schemaVersion": 1,
        "label": "context tax",
        "message": f"{tokens:,} tokens",
        "color": badge_color(tokens),
    }


def write_badge(report, path) -> None:
    """Write the shields.io endpoint document for *report* to *path*."""
    doc = json.dumps(badge_doc(report), indent=2)
    Path(path).write_text(doc + "\n", encoding="utf-8")
