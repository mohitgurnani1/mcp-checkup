# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

from mcp_checkup.checks import Finding, Severity
from mcp_checkup.discovery.base import Discovered
from mcp_checkup.html_report import scan_to_html
from mcp_checkup.models import ServerInventory, ServerSpec, ToolInfo, Transport
from mcp_checkup.scan import ScanEntry, ScanReport
from mcp_checkup.tokens import weigh_inventory


def _tool(name: str, description: str = "does something useful") -> ToolInfo:
    return ToolInfo(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )


def _entry(name: str, tools: list[ToolInfo], client: str = "cursor") -> ScanEntry:
    spec = ServerSpec(name=name, transport=Transport.STDIO, command="python", args=["srv.py"])
    d = Discovered(spec=spec, client=client, source=f"/fake/{client}.json")
    inv = ServerInventory(spec=spec, tools=tools)
    return ScanEntry(discovered=d, clients=[client], result=weigh_inventory(inv))


def _error_entry(name: str) -> ScanEntry:
    spec = ServerSpec(name=name, transport=Transport.STDIO, command="python", args=["dead.py"])
    d = Discovered(spec=spec, client="vscode", source="/fake/vscode.json")
    return ScanEntry(discovered=d, clients=["vscode"], error="boom")


def _report() -> ScanReport:
    return ScanReport(
        entries=[_entry("toy", [_tool("alpha"), _tool("beta")]), _error_entry("dead")]
    )


def test_contains_servers_counts_and_totals() -> None:
    report = _report()
    doc = scan_to_html(report)
    assert "🩺 MCP Checkup" in doc
    assert "toy" in doc
    assert "dead" in doc
    assert "cursor" in doc
    anthropic = report.totals()["anthropic"]
    assert f"{anthropic:,}" in doc
    # summary tiles: servers / tools / anthropic tokens
    assert ">2</div>" in doc  # 2 servers and 2 tools
    assert "anthropic tokens" in doc


def test_escapes_injected_server_name() -> None:
    evil = "<script>alert(1)</script>"
    report = ScanReport(entries=[_entry(evil, [_tool("alpha")])])
    doc = scan_to_html(report)
    assert "<script" not in doc
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in doc


def test_escapes_injected_error_and_generated_at() -> None:
    entry = _error_entry("dead")
    entry.error = '<img src="x">'
    doc = scan_to_html(ScanReport(entries=[entry]), generated_at="<b>now</b>")
    assert "<img" not in doc
    assert "&lt;img" in doc
    assert "<b>now</b>" not in doc
    assert "&lt;b&gt;now&lt;/b&gt;" in doc


def test_fully_self_contained() -> None:
    doc = scan_to_html(_report())
    assert "http" not in doc  # no external URLs at all
    assert "cdn" not in doc.lower()
    assert "@import" not in doc
    assert "src=" not in doc
    assert "<style>" in doc  # styling is inline


def test_dark_mode_media_query_present() -> None:
    doc = scan_to_html(_report())
    assert "prefers-color-scheme: dark" in doc


def test_deterministic_with_fixed_generated_at() -> None:
    ts = "2026-07-06 12:00 UTC"
    a = scan_to_html(_report(), generated_at=ts)
    b = scan_to_html(_report(), generated_at=ts)
    assert a == b
    assert f"Generated {ts}" in a


def test_generated_line_omitted_when_empty() -> None:
    assert "Generated" not in scan_to_html(_report())


def test_error_row_styled() -> None:
    doc = scan_to_html(_report())
    assert 'class="error"' in doc
    assert "error: boom" in doc


def test_cost_table_rendered_from_costs_doc_shape() -> None:
    costs = [
        {
            "model": "claude-sonnet-4",
            "provider": "anthropic",
            "tokens": 1234,
            "usd_per_request": 0.0037,
            "usd_per_session": 0.04,
            "turns": 10,
            "context_pct": 0.62,
        }
    ]
    doc = scan_to_html(_report(), costs=costs)
    assert "Context tax per model" in doc
    assert "claude-sonnet-4" in doc
    assert "1,234" in doc
    assert "$0.0037" in doc
    assert "$0.04" in doc
    assert "0.6%" in doc
    assert "$/session (10 turns)" in doc


def test_no_cost_table_without_costs() -> None:
    assert "Context tax per model" not in scan_to_html(_report())


def test_findings_grouped_by_severity() -> None:
    report = _report()
    report.findings = [
        Finding("H01", Severity.HIGH, "toy", "prompt injection suspected", tool="alpha"),
        Finding("W01", Severity.LOW, "toy", "chatty description"),
        Finding("W02", Severity.MEDIUM, "toy", "huge schema"),
    ]
    doc = scan_to_html(report)
    assert "Hygiene findings (3)" in doc
    assert "High (1)" in doc
    assert "Medium (1)" in doc
    assert "Low (1)" in doc
    assert "H01" in doc
    assert "toy &gt; alpha" in doc  # tool-scoped location, escaped
    # severity groups come out high -> medium -> low
    assert doc.index("High (1)") < doc.index("Medium (1)") < doc.index("Low (1)")
    # per-server hygiene cell summarizes counts
    assert "1 high" in doc


def test_empty_severity_groups_omitted() -> None:
    report = _report()
    report.findings = [Finding("W01", Severity.LOW, "toy", "chatty description")]
    doc = scan_to_html(report)
    assert "Low (1)" in doc
    assert "High (" not in doc
    assert "Medium (" not in doc


def test_hygiene_ok_and_footnotes() -> None:
    doc = scan_to_html(_report())
    assert "✓ ok" in doc
    assert "estimates" in doc
    assert "Context tax:" in doc  # anthropic context-tax line incl. overhead
