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


def scan_to_json(report) -> str:
    """JSON document for a full scan (ScanReport)."""
    servers = []
    for e in report.entries:
        item: dict[str, Any] = {
            "name": e.discovered.spec.name,
            "transport": e.discovered.spec.transport.value,
            "clients": e.clients,
            "source": e.discovered.source,
        }
        if e.error:
            item["error"] = e.error
        if e.result:
            item["totals"] = e.result.totals()
            item["tools"] = [
                {"name": tw.tool.name, "tokens": tw.tokens} for tw in e.result.tool_weights
            ]
        servers.append(item)
    doc = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "servers": servers,
        "totals": report.totals(),
        "findings": findings_doc(getattr(report, "findings", [])),
        "note": "Token counts are estimates (tiktoken o200k_base on provider wire JSON).",
    }
    return json.dumps(doc, indent=2)


def _hygiene_cell(server: str, findings) -> str:
    mine = [f for f in findings if f.server == server]
    if not mine:
        return "[green]✓ ok[/green]"
    by_sev: dict[str, int] = {}
    for f in mine:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
    parts = []
    for sev, color in (("high", "red"), ("medium", "yellow"), ("low", "dim")):
        if by_sev.get(sev):
            parts.append(f"[{color}]{by_sev[sev]} {sev}[/{color}]")
    return "⚠ " + ", ".join(parts)


def print_findings(findings, verbose: bool = False, console: Console | None = None) -> None:
    """Detail list of hygiene findings below the main table."""
    console = console or Console()
    if not findings:
        return
    console.print(f"\n[bold]Hygiene findings ({len(findings)})[/bold]")
    color = {"high": "red", "medium": "yellow", "low": "dim"}
    for f in findings:
        c = color[f.severity.value]
        loc = f.server + (f" > {f.tool}" if f.tool else "")
        console.print(f"  [{c}]{f.check_id} {f.severity.value:<6}[/{c}] {loc}: {f.summary}")
        if verbose and f.detail:
            console.print(f"           [dim]{f.detail}[/dim]")


def findings_doc(findings) -> list[dict[str, Any]]:
    return [
        {
            "check": f.check_id,
            "severity": f.severity.value,
            "server": f.server,
            "tool": f.tool,
            "summary": f.summary,
            "detail": f.detail,
        }
        for f in findings
    ]


def print_scan_table(report, console: Console | None = None) -> None:
    """Aggregate table: one row per discovered server."""
    console = console or Console()
    ok = [e for e in report.entries if e.result]
    findings = getattr(report, "findings", [])

    table = Table(
        title=f"🩺 MCP Checkup — {len(report.entries)} server(s), {report.tool_count} tools",
        title_justify="left",
    )
    table.add_column("Server", style="bold")
    table.add_column("Clients")
    table.add_column("Tools", justify="right")
    for provider in PROVIDERS:
        table.add_column(provider, justify="right")
    table.add_column("Hygiene")

    for e in sorted(
        report.entries,
        key=lambda e: -(e.result.totals().get("anthropic", 0) if e.result else -1),
    ):
        name = e.discovered.spec.name
        clients = ", ".join(e.clients)
        if e.result:
            totals = e.result.totals()
            table.add_row(
                name,
                clients,
                str(len(e.result.tool_weights)),
                *[f"{totals.get(p, 0):,}" for p in PROVIDERS],
                _hygiene_cell(name, findings),
            )
        else:
            table.add_row(
                name, clients, "-", f"[red]{e.error or 'unknown error'}[/red]", "", "", ""
            )

    if ok:
        totals = report.totals()
        table.add_section()
        table.add_row(
            "[bold]Total[/bold]",
            "",
            f"[bold]{report.tool_count}[/bold]",
            *[f"[bold]{totals.get(p, 0):,}[/bold]" for p in PROVIDERS],
        )

    console.print(table)
    if ok:
        anthropic_total = report.totals().get("anthropic", 0) + system_overhead("anthropic")
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


def costs_doc(totals: dict[str, int], models, turns: int) -> list[dict[str, Any]]:
    """JSON cost entries for the given per-provider token totals."""
    from mcp_checkup.pricing import cost_line

    out = []
    for m in models:
        tokens = totals.get(m.provider, 0) + system_overhead(m.provider)
        c = cost_line(m, tokens, turns=turns)
        out.append(
            {
                "model": m.key,
                "provider": m.provider,
                "tokens": tokens,
                "usd_per_request": round(c.usd_per_request, 6),
                "usd_per_session": round(c.usd_per_session, 6),
                "turns": turns,
                "context_pct": round(c.context_pct, 2),
            }
        )
    return out


def print_cost_section(
    totals: dict[str, int], models, turns: int, console: Console | None = None
) -> None:
    """Per-model cost + context-tax lines under a weigh/scan table."""
    from mcp_checkup.pricing import cost_line

    console = console or Console()
    table = Table(title="💸 Context tax per model", title_justify="left")
    table.add_column("Model", style="bold")
    table.add_column("Tokens", justify="right")
    table.add_column("$/request", justify="right")
    table.add_column(f"$/session ({turns} turns)", justify="right")
    table.add_column("% of context", justify="right")

    for m in models:
        tokens = totals.get(m.provider, 0) + system_overhead(m.provider)
        c = cost_line(m, tokens, turns=turns)
        table.add_row(
            m.display,
            f"{tokens:,}",
            f"${c.usd_per_request:.4f}",
            f"${c.usd_per_session:.2f}",
            f"{c.context_pct:.1f}%",
        )
    console.print(table)
    console.print(
        "[dim]$/session assumes schemas resent every turn (no prompt caching); "
        "with caching you pay full price on turn one and on every cache miss.[/dim]"
    )


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
