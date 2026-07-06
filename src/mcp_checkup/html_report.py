# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Render a ScanReport as a single self-contained HTML page.

Built for sharing in Slack threads and PR descriptions: inline CSS only, a
system font stack, and zero external requests (no fonts, scripts, images, or
stylesheets). Light/dark follows ``prefers-color-scheme``. Every dynamic
string is escaped with :func:`html.escape` before it reaches the document.
"""

from __future__ import annotations

from html import escape

from mcp_checkup.models import PROVIDERS
from mcp_checkup.tokens import system_overhead

_SEVERITIES = (("high", "High"), ("medium", "Medium"), ("low", "Low"))

_ESTIMATES_FOOTNOTE = (
    "Token counts are estimates (tiktoken o200k_base on provider wire JSON); "
    "exact for GPT-4o-family, proxy for others."
)

_STYLE = """\
:root {
  --bg: #ffffff; --fg: #1b1f24; --muted: #67707b; --border: #d9dee3;
  --tile: #f4f6f8; --ok: #067647; --high: #b42318; --medium: #b54708; --low: #67707b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1216; --fg: #e7ebef; --muted: #97a1ab; --border: #2b323a;
    --tile: #1a2027; --ok: #47cd89; --high: #f97066; --medium: #fdb022; --low: #97a1ab;
  }
}
body {
  margin: 2rem auto; max-width: 60rem; padding: 0 1rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--fg); line-height: 1.5;
}
h1 { font-size: 1.4rem; margin-bottom: .25rem; }
h2 { font-size: 1.1rem; margin-top: 1.75rem; }
h3 { font-size: .95rem; margin-bottom: .25rem; }
.generated { color: var(--muted); font-size: .85rem; margin-top: 0; }
.tiles { display: flex; gap: .75rem; flex-wrap: wrap; margin: 1rem 0; }
.tile {
  background: var(--tile); border: 1px solid var(--border);
  border-radius: 8px; padding: .75rem 1.25rem; min-width: 7rem;
}
.tile .num { font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.tile .label {
  color: var(--muted); font-size: .75rem;
  text-transform: uppercase; letter-spacing: .04em;
}
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
th, td { border-bottom: 1px solid var(--border); padding: .4rem .6rem; text-align: left; }
th { color: var(--muted); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tfoot td { font-weight: 700; border-top: 2px solid var(--border); border-bottom: none; }
tr.error td { color: var(--high); }
.ok { color: var(--ok); }
.sev-high { color: var(--high); }
.sev-medium { color: var(--medium); }
.sev-low { color: var(--low); }
ul.findings { list-style: none; padding-left: 0; margin-top: .25rem; }
ul.findings li { border-left: 3px solid var(--border); padding: .2rem .6rem; margin: .25rem 0; }
li.li-high { border-left-color: var(--high); }
li.li-medium { border-left-color: var(--medium); }
li.li-low { border-left-color: var(--low); }
code { background: var(--tile); border-radius: 4px; padding: 0 .3em; font-size: .85em; }
.tax { font-weight: 500; }
.footnote { color: var(--muted); font-size: .8rem; margin-top: 1.5rem; }
"""


def _n(value: int) -> str:
    return f"{value:,}"


def _hygiene_cell(server: str, findings) -> str:
    mine = [f for f in findings if f.server == server]
    if not mine:
        return '<span class="ok">✓ ok</span>'
    by_sev: dict[str, int] = {}
    for f in mine:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
    parts = [
        f'<span class="sev-{sev}">{by_sev[sev]} {sev}</span>'
        for sev, _ in _SEVERITIES
        if by_sev.get(sev)
    ]
    return "⚠ " + ", ".join(parts)


def _tiles(report) -> list[str]:
    anthropic = report.totals().get("anthropic", 0)
    out = ['<section class="tiles">']
    for value, label in (
        (str(len(report.entries)), "servers"),
        (str(report.tool_count), "tools"),
        (_n(anthropic), "anthropic tokens"),
    ):
        out.append(
            f'<div class="tile"><div class="num">{escape(value)}</div>'
            f'<div class="label">{escape(label)}</div></div>'
        )
    out.append("</section>")
    return out


def _server_table(report, findings) -> list[str]:
    ok = [e for e in report.entries if e.result]
    headers = "".join(
        f'<th class="{cls}">{escape(h)}</th>'
        for h, cls in (
            ("Server", ""),
            ("Clients", ""),
            ("Tools", "num"),
            *((p, "num") for p in PROVIDERS),
            ("Hygiene", ""),
        )
    )
    out = ["<table>", f"<thead><tr>{headers}</tr></thead>", "<tbody>"]
    for e in sorted(
        report.entries,
        key=lambda e: -(e.result.totals().get("anthropic", 0) if e.result else -1),
    ):
        name = escape(e.discovered.spec.name)
        clients = escape(", ".join(e.clients))
        if e.result:
            totals = e.result.totals()
            cells = [
                f"<td>{name}</td>",
                f"<td>{clients}</td>",
                f'<td class="num">{len(e.result.tool_weights)}</td>',
                *(f'<td class="num">{_n(totals.get(p, 0))}</td>' for p in PROVIDERS),
                f"<td>{_hygiene_cell(e.discovered.spec.name, findings)}</td>",
            ]
            out.append("<tr>" + "".join(cells) + "</tr>")
        else:
            err = escape(e.error or "unknown error")
            out.append(
                f'<tr class="error"><td>{name}</td><td>{clients}</td>'
                '<td class="num">-</td>'
                f'<td colspan="{len(PROVIDERS)}">error: {err}</td><td></td></tr>'
            )
    out.append("</tbody>")
    if ok:
        totals = report.totals()
        foot = [
            "<td>Total</td>",
            "<td></td>",
            f'<td class="num">{report.tool_count}</td>',
            *(f'<td class="num">{_n(totals.get(p, 0))}</td>' for p in PROVIDERS),
            "<td></td>",
        ]
        out.append("<tfoot><tr>" + "".join(foot) + "</tr></tfoot>")
    out.append("</table>")
    return out


def _cost_table(costs: list[dict]) -> list[str]:
    turns = costs[0].get("turns", 10)
    headers = "".join(
        f'<th class="{cls}">{escape(h)}</th>'
        for h, cls in (
            ("Model", ""),
            ("Tokens", "num"),
            ("$/request", "num"),
            (f"$/session ({turns} turns)", "num"),
            ("% of context", "num"),
        )
    )
    out = [
        "<h2>💸 Context tax per model</h2>",
        "<table>",
        f"<thead><tr>{headers}</tr></thead>",
        "<tbody>",
    ]
    for c in costs:
        out.append(
            "<tr>"
            f"<td>{escape(str(c['model']))}</td>"
            f'<td class="num">{_n(int(c["tokens"]))}</td>'
            f'<td class="num">${c["usd_per_request"]:.4f}</td>'
            f'<td class="num">${c["usd_per_session"]:.2f}</td>'
            f'<td class="num">{c["context_pct"]:.1f}%</td>'
            "</tr>"
        )
    out += ["</tbody>", "</table>"]
    return out


def _findings_section(findings) -> list[str]:
    out = [f"<h2>Hygiene findings ({len(findings)})</h2>"]
    for sev, label in _SEVERITIES:
        mine = [f for f in findings if f.severity.value == sev]
        if not mine:
            continue
        out.append(f'<h3 class="sev-{sev}">{escape(label)} ({len(mine)})</h3>')
        out.append('<ul class="findings">')
        for f in mine:
            loc = f.server + (f" > {f.tool}" if f.tool else "")
            out.append(
                f'<li class="li-{sev}"><code>{escape(f.check_id)}</code> '
                f"{escape(loc)}: {escape(f.summary)}</li>"
            )
        out.append("</ul>")
    return out


def scan_to_html(report, costs: list[dict] | None = None, generated_at: str = "") -> str:
    """Self-contained HTML document for a full scan (ScanReport).

    *costs* takes the same dicts as :func:`mcp_checkup.render.costs_doc`
    output; when given, a per-model cost table is included. *generated_at* is
    an already-formatted timestamp string supplied by the caller — this
    function never reads the clock, so output is deterministic.
    """
    findings = getattr(report, "findings", [])
    ok = [e for e in report.entries if e.result]

    body: list[str] = [
        "<header>",
        "<h1>🩺 MCP Checkup</h1>",
    ]
    if generated_at:
        body.append(f'<p class="generated">Generated {escape(generated_at)}</p>')
    body.append("</header>")

    body += _tiles(report)
    body += _server_table(report, findings)

    if ok:
        anthropic_total = report.totals().get("anthropic", 0) + system_overhead("anthropic")
        body.append(
            f'<p class="tax">Context tax: ~{_n(anthropic_total)} tokens on Anthropic models '
            f"(incl. {system_overhead('anthropic')} tool-use system overhead), "
            "before your first message.</p>"
        )

    if costs:
        body += _cost_table(costs)
    if findings:
        body += _findings_section(findings)

    body.append(f'<p class="footnote">{escape(_ESTIMATES_FOOTNOTE)}</p>')

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>MCP Checkup</title>\n"
        "<style>\n" + _STYLE + "</style>\n"
        "</head>\n"
        "<body>\n" + "\n".join(body) + "\n</body>\n"
        "</html>\n"
    )
