# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

from mcp_checkup.checks.base import Finding, Severity
from mcp_checkup.discovery.base import Discovered
from mcp_checkup.markdown import scan_to_markdown
from mcp_checkup.models import ServerInventory, ServerSpec, ToolInfo, Transport
from mcp_checkup.scan import ScanEntry, ScanReport
from mcp_checkup.tokens import weigh_inventory


def _entry(name: str, tools: list[ToolInfo], client: str = "cursor") -> ScanEntry:
    spec = ServerSpec(name=name, transport=Transport.STDIO, command="python", args=[f"{name}.py"])
    d = Discovered(spec=spec, client=client, source=f"/fake/{client}.json")
    inv = ServerInventory(spec=spec, tools=tools)
    return ScanEntry(discovered=d, clients=[client], result=weigh_inventory(inv))


def _report() -> ScanReport:
    tool = ToolInfo(
        name="fetch",
        description="fetch a url",
        input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
    )
    ok = _entry("toy", [tool])
    dead_spec = ServerSpec(name="dead", transport=Transport.STDIO, command="python")
    dead = ScanEntry(
        discovered=Discovered(spec=dead_spec, client="vscode", source="/fake/vscode.json"),
        clients=["vscode"],
        error="connection refused",
    )
    findings = [
        Finding(
            check_id="W01",
            severity=Severity.HIGH,
            server="toy",
            tool="fetch",
            summary="tool description is enormous",
        ),
        Finding(
            check_id="S02",
            severity=Severity.LOW,
            server="toy",
            summary="tool name shadows another server",
        ),
    ]
    return ScanReport(entries=[ok, dead], findings=findings)


def test_markdown_header_and_table() -> None:
    md = scan_to_markdown(_report())
    assert md.startswith("### 🩺 MCP Checkup")
    assert "| Server" in md
    assert "| Clients" in md
    assert "| anthropic" in md
    assert "| openai" in md
    assert "| gemini" in md
    assert "| Hygiene" in md
    assert "**Total**" in md
    # error row is inline in the table
    error_rows = [ln for ln in md.splitlines() if "dead" in ln]
    assert any("error: connection refused" in ln and ln.startswith("|") for ln in error_rows)


def test_markdown_findings_and_footnote() -> None:
    md = scan_to_markdown(_report())
    assert "#### Hygiene findings (2)" in md
    assert "- **high** W01 `toy > fetch`: tool description is enormous" in md
    assert "- **low** S02 `toy`: tool name shadows another server" in md
    assert "estimates" in md
    assert "tiktoken o200k_base" in md


def test_markdown_hygiene_cells() -> None:
    md = scan_to_markdown(_report())
    toy_row = next(ln for ln in md.splitlines() if ln.startswith("| toy"))
    assert "1 high" in toy_row
    assert "1 low" in toy_row


def test_markdown_no_ansi_no_rich() -> None:
    md = scan_to_markdown(_report())
    assert "\x1b" not in md
    assert "[bold]" not in md
    assert "[red]" not in md


def test_markdown_costs_table() -> None:
    costs = [
        {
            "model": "claude-sonnet-4-5",
            "provider": "anthropic",
            "tokens": 1546,
            "usd_per_request": 0.004638,
            "usd_per_session": 0.046380,
            "turns": 10,
            "context_pct": 0.77,
        },
        {
            "model": "gpt-4o",
            "provider": "openai",
            "tokens": 1100,
            "usd_per_request": 0.00275,
            "usd_per_session": 0.0275,
            "turns": 10,
            "context_pct": 0.86,
        },
    ]
    md = scan_to_markdown(_report(), costs=costs)
    assert "#### 💸 Context tax per model" in md
    assert "$/session (10 turns)" in md
    assert "claude-sonnet-4-5" in md
    assert "$0.0046" in md
    assert "0.8%" in md or "0.9%" in md


def test_markdown_no_costs_section_when_omitted() -> None:
    md = scan_to_markdown(_report())
    assert "Context tax per model" not in md


def test_markdown_columns_align() -> None:
    md = scan_to_markdown(_report())
    table = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert len(table) >= 4  # header, separator, 2 servers (+ total)
    assert len({len(ln) for ln in table}) == 1  # every row padded to same width
