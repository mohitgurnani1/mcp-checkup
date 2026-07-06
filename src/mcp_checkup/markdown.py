# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Render a ScanReport as GitHub-flavored markdown (for PR comments / CI logs).

Plain text only: no rich markup, no ANSI escapes. Columns are padded so the
raw markdown stays readable before GitHub renders it.
"""

from __future__ import annotations

from mcp_checkup.models import PROVIDERS
from mcp_checkup.tokens import system_overhead

_ESTIMATES_FOOTNOTE = (
    "_Token counts are estimates (tiktoken o200k_base on provider wire JSON); "
    "exact for GPT-4o-family, proxy for others._"
)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Markdown table lines with cells padded to per-column width."""
    widths = []
    for i, header in enumerate(headers):
        widths.append(max(3, len(header), *(len(row[i]) for row in rows)) if rows else 3)

    def fmt(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)) + " |"

    lines = [fmt(headers), "| " + " | ".join("-" * w for w in widths) + " |"]
    lines.extend(fmt(row) for row in rows)
    return lines


def _hygiene_cell(server: str, findings) -> str:
    mine = [f for f in findings if f.server == server]
    if not mine:
        return "✓ ok"
    by_sev: dict[str, int] = {}
    for f in mine:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
    parts = [f"{by_sev[sev]} {sev}" for sev in ("high", "medium", "low") if by_sev.get(sev)]
    return "⚠ " + ", ".join(parts)


def scan_to_markdown(report, costs: list[dict] | None = None) -> str:
    """GitHub-flavored markdown for a full scan (ScanReport).

    *costs* takes the same dicts as :func:`mcp_checkup.render.costs_doc`
    output; when given, a per-model cost table is included.
    """
    findings = getattr(report, "findings", [])
    ok = [e for e in report.entries if e.result]

    lines = [
        "### 🩺 MCP Checkup",
        "",
        f"{len(report.entries)} server(s), {report.tool_count} tools",
        "",
    ]

    headers = ["Server", "Clients", "Tools", *PROVIDERS, "Hygiene"]
    rows = []
    for e in sorted(
        report.entries,
        key=lambda e: -(e.result.totals().get("anthropic", 0) if e.result else -1),
    ):
        name = e.discovered.spec.name
        clients = ", ".join(e.clients)
        if e.result:
            totals = e.result.totals()
            rows.append(
                [
                    name,
                    clients,
                    str(len(e.result.tool_weights)),
                    *[f"{totals.get(p, 0):,}" for p in PROVIDERS],
                    _hygiene_cell(name, findings),
                ]
            )
        else:
            rows.append([name, clients, "-", f"error: {e.error or 'unknown error'}", "", "", ""])
    if ok:
        totals = report.totals()
        rows.append(
            [
                "**Total**",
                "",
                f"**{report.tool_count}**",
                *[f"**{totals.get(p, 0):,}**" for p in PROVIDERS],
                "",
            ]
        )
    lines.extend(_table(headers, rows))

    if ok:
        anthropic_total = report.totals().get("anthropic", 0) + system_overhead("anthropic")
        lines += [
            "",
            f"Context tax: ~{anthropic_total:,} tokens on Anthropic models "
            f"(incl. {system_overhead('anthropic')} tool-use system overhead), "
            "before your first message.",
        ]

    if costs:
        turns = costs[0].get("turns", 10)
        lines += ["", "#### 💸 Context tax per model", ""]
        cost_rows = [
            [
                c["model"],
                f"{c['tokens']:,}",
                f"${c['usd_per_request']:.4f}",
                f"${c['usd_per_session']:.2f}",
                f"{c['context_pct']:.1f}%",
            ]
            for c in costs
        ]
        lines.extend(
            _table(
                ["Model", "Tokens", "$/request", f"$/session ({turns} turns)", "% of context"],
                cost_rows,
            )
        )

    if findings:
        lines += ["", f"#### Hygiene findings ({len(findings)})", ""]
        for f in findings:
            loc = f.server + (f" > {f.tool}" if f.tool else "")
            lines.append(f"- **{f.severity.value}** {f.check_id} `{loc}`: {f.summary}")

    lines += ["", _ESTIMATES_FOOTNOTE, ""]
    return "\n".join(lines)
