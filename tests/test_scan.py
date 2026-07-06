# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import sys

from rich.console import Console

from mcp_checkup.discovery.base import Discovered
from mcp_checkup.models import ServerSpec, Transport
from mcp_checkup.render import print_scan_table, scan_to_json
from mcp_checkup.scan import ScanReport, dedupe, run_scan


def _disc(name: str, client: str, command: str = "python", args: list[str] | None = None):
    spec = ServerSpec(name=name, transport=Transport.STDIO, command=command, args=args or [])
    return Discovered(spec=spec, client=client, source=f"/fake/{client}.json")


def test_dedupe_merges_same_server_across_clients() -> None:
    found = [
        _disc("fs", "claude-desktop", args=["srv.py"]),
        _disc("filesystem", "cursor", args=["srv.py"]),
        _disc("other", "cursor", args=["other.py"]),
    ]
    entries = dedupe(found)
    assert len(entries) == 2
    merged = next(e for e in entries if e.discovered.spec.name == "fs")
    assert sorted(merged.clients) == ["claude-desktop", "cursor"]


def test_dedupe_keeps_needs_input_error() -> None:
    d = _disc("vs", "vscode")
    d.error = "needs-input"
    entries = dedupe([d])
    assert entries[0].error == "needs-input"


def test_run_scan_weighs_real_fixture(tmp_path, monkeypatch) -> None:
    # Fake home containing only a cursor config pointing at the toy server.
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    (cursor_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "toy": {
                        "command": sys.executable,
                        "args": ["tests/fixtures/toy_server.py"],
                    }
                }
            }
        )
    )
    report = asyncio.run(run_scan(home=tmp_path, clients=["cursor"], timeout=15))
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.error is None
    assert entry.result is not None
    assert report.totals()["anthropic"] > 0
    assert report.tool_count == 3


def test_run_scan_error_row(tmp_path) -> None:
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    (cursor_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"broken": {"command": sys.executable, "args": ["-c", "pass"]}}})
    )
    report = asyncio.run(run_scan(home=tmp_path, clients=["cursor"], timeout=3))
    assert report.entries[0].error
    assert report.entries[0].result is None


def test_scan_render_and_json() -> None:
    ok = _disc("toy", "cursor")
    entry_err = dedupe([_disc("dead", "vscode")])[0]
    entry_err.error = "boom"
    report = ScanReport(entries=[*dedupe([ok]), entry_err])

    doc = json.loads(scan_to_json(report))
    assert doc["schema_version"] == 1
    names = {s["name"] for s in doc["servers"]}
    assert names == {"toy", "dead"}
    assert doc["servers"][1]["error"] == "boom" or doc["servers"][0]["error"] == "boom"

    console = Console(record=True, width=120)
    print_scan_table(report, console=console)
    out = console.export_text()
    assert "dead" in out
    assert "boom" in out


def test_env_values_never_rendered() -> None:
    spec = ServerSpec(
        name="secretive",
        transport=Transport.STDIO,
        command="python",
        env={"API_KEY": "super-secret-value"},
    )
    d = Discovered(spec=spec, client="cursor", source="/fake/cursor.json")
    report = ScanReport(entries=dedupe([d]))
    report.entries[0].error = "unreachable"

    console = Console(record=True, width=120)
    print_scan_table(report, console=console)
    assert "super-secret-value" not in console.export_text()
    assert "super-secret-value" not in scan_to_json(report)
