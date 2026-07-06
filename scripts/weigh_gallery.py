# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Regenerate docs/GALLERY.md: measured context tax of popular MCP servers.

Run manually before releases: `uv run python scripts/weigh_gallery.py`.
Servers needing credentials are attempted anyway — tools/list often works
without auth; failures are recorded honestly.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcp_checkup.tokens import weigh_inventory
from mcp_checkup.transport import TransportError, fetch_inventory, parse_target

SERVERS: list[tuple[str, str]] = [
    ("everything (reference)", "npx -y @modelcontextprotocol/server-everything"),
    ("filesystem", "npx -y @modelcontextprotocol/server-filesystem /tmp"),
    ("memory", "npx -y @modelcontextprotocol/server-memory"),
    ("sequential-thinking", "npx -y @modelcontextprotocol/server-sequential-thinking"),
    ("github", "npx -y @modelcontextprotocol/server-github"),
    ("playwright", "npx -y @playwright/mcp@latest"),
    ("puppeteer", "npx -y puppeteer-mcp-server"),
    ("brave-search", "npx -y @modelcontextprotocol/server-brave-search"),
    ("fetch", "uvx mcp-server-fetch"),
    ("git", "uvx mcp-server-git"),
    ("time", "uvx mcp-server-time"),
]


async def measure(name: str, command: str) -> tuple[str, int, int] | tuple[str, None, str]:
    try:
        inv = await fetch_inventory(parse_target(command), timeout=90)
    except TransportError as exc:
        return (name, None, str(exc).split(":")[-1].strip()[:60])
    result = weigh_inventory(inv)
    return (name, result.totals().get("anthropic", 0), len(result.tool_weights))


async def main() -> None:
    rows = []
    for name, command in SERVERS:
        print(f"weighing {name}...", file=sys.stderr)
        rows.append(await measure(name, command))

    ok = sorted((r for r in rows if r[1] is not None), key=lambda r: -r[1])
    failed = [r for r in rows if r[1] is None]

    lines = [
        "# Context-tax gallery",
        "",
        "Measured tool-definition weight (Anthropic wire format, tiktoken",
        "`o200k_base`) of popular MCP servers. Regenerate with",
        "`uv run python scripts/weigh_gallery.py`.",
        "",
        f"_Last measured: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}._",
        "",
        "| Server | Tools | Tokens/request |",
        "| --- | ---: | ---: |",
    ]
    for name, tokens, tool_count in ok:
        lines.append(f"| {name} | {tool_count} | {tokens:,} |")
    if failed:
        lines += ["", "Not measurable in this run:", ""]
        for name, _, reason in failed:
            lines.append(f"- {name}: {reason}")
    lines.append("")

    out = Path(__file__).resolve().parent.parent / "docs" / "GALLERY.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
