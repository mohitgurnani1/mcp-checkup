# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Render a WeighResult as a rich table or JSON."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from mcp_checkup.models import PROVIDERS, REPORT_SCHEMA_VERSION, WeighResult
from mcp_checkup.tokens import system_overhead


def to_json(result: WeighResult) -> str:
    doc: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "server": {
            "name": result.inventory.spec.name,
            "transport": result.inventory.spec.transport.value,
        },
        "tools": [
            {
                "name": tw.tool.name,
                "description_chars": len(tw.tool.description),
                "tokens": tw.tokens,
            }
            for tw in result.tool_weights
        ],
        "resources": {"count": len(result.inventory.resources), "tokens": result.resource_tokens},
        "prompts": {"count": len(result.inventory.prompts), "tokens": result.prompt_tokens},
        "totals": result.totals(),
        "system_overhead": {p: system_overhead(p) for p in PROVIDERS},
        "note": "Token counts are estimates (tiktoken o200k_base on provider wire JSON).",
    }
    return json.dumps(doc, indent=2)


def print_table(result: WeighResult, console: Console | None = None) -> None:
    console = console or Console()
    spec = result.inventory.spec

    table = Table(
        title=f"🩺 {spec.name} — {len(result.tool_weights)} tools",
        title_justify="left",
    )
    table.add_column("Tool", style="bold")
    for provider in PROVIDERS:
        table.add_column(provider, justify="right")

    for tw in sorted(result.tool_weights, key=lambda t: -max(t.tokens.values(), default=0)):
        table.add_row(tw.tool.name, *[f"{tw.tokens.get(p, 0):,}" for p in PROVIDERS])

    if result.inventory.resources:
        table.add_row(
            f"[dim]{len(result.inventory.resources)} resource(s)[/dim]",
            *[f"[dim]{result.resource_tokens.get(p, 0):,}[/dim]" for p in PROVIDERS],
        )
    if result.inventory.prompts:
        table.add_row(
            f"[dim]{len(result.inventory.prompts)} prompt(s)[/dim]",
            *[f"[dim]{result.prompt_tokens.get(p, 0):,}[/dim]" for p in PROVIDERS],
        )

    totals = result.totals()
    table.add_section()
    table.add_row(
        "[bold]Total (tool definitions)[/bold]",
        *[f"[bold]{totals.get(p, 0):,}[/bold]" for p in PROVIDERS],
    )

    console.print(table)
    anthropic_total = totals.get("anthropic", 0) + system_overhead("anthropic")
    console.print(
        f"Context tax: ~{anthropic_total:,} tokens on Anthropic models "
        f"(incl. {system_overhead('anthropic')} tool-use system overhead), "
        "before your first message.",
        highlight=False,
    )
    console.print(
        "[dim]Estimates via tiktoken o200k_base on provider wire JSON; "
        "exact for GPT-4o-family, proxy for others.[/dim]"
    )
