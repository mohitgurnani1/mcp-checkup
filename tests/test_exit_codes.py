# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Exit-code contract: 0 ok, 1 budget, 2 hygiene, 3 all servers unreachable."""

import json
import sys

import pytest

from mcp_checkup.cli import main


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Home with one cursor config pointing at the toy fixture server."""
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    (cursor / "mcp.json").write_text(
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
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path


@pytest.mark.integration
def test_exit_0_within_budget(fake_home) -> None:
    assert main(["scan", "--client", "cursor", "--quiet", "--fail-over", "5000"]) == 0


@pytest.mark.integration
def test_exit_1_budget_exceeded(fake_home, capsys) -> None:
    assert main(["scan", "--client", "cursor", "--quiet", "--fail-over", "100"]) == 1
    assert "budget exceeded" in capsys.readouterr().err


@pytest.mark.integration
def test_exit_1_total_budget(fake_home, capsys) -> None:
    assert main(["scan", "--client", "cursor", "--quiet", "--fail-over-total", "100"]) == 1


@pytest.mark.integration
def test_exit_2_hygiene_low(fake_home, capsys) -> None:
    # The toy server has no findings at all; force severity 'low' with a
    # poisoned config server name is overkill — instead assert 0 here and
    # exercise exit 2 through the unit path below.
    assert main(["scan", "--client", "cursor", "--quiet", "--fail-on-severity", "low"]) == 0


def test_exit_2_unit(monkeypatch, capsys) -> None:
    from argparse import Namespace

    from mcp_checkup.checks.base import Finding, Severity
    from mcp_checkup.cli import _scan_exit_code
    from mcp_checkup.scan import ScanReport

    report = ScanReport(
        entries=[],
        findings=[Finding("H02", Severity.HIGH, "srv", "poisoned")],
    )
    args = Namespace(fail_over=None, fail_over_total=None, fail_on_severity="medium")
    assert _scan_exit_code(args, report) == 2
    assert "hygiene gate" in capsys.readouterr().err


@pytest.mark.integration
def test_exit_3_all_unreachable(tmp_path, monkeypatch, capsys) -> None:
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    (cursor / "mcp.json").write_text(
        json.dumps({"mcpServers": {"dead": {"command": sys.executable, "args": ["-c", "pass"]}}})
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert main(["scan", "--client", "cursor", "--quiet", "--timeout", "3"]) == 3


@pytest.mark.integration
def test_baseline_write_and_compare(fake_home, capsys, tmp_path) -> None:
    base = str(tmp_path / "base.json")
    assert main(["scan", "--client", "cursor", "--quiet", "--write-baseline", base]) == 0
    assert "baseline written" in capsys.readouterr().err
    assert main(["scan", "--client", "cursor", "--quiet", "--baseline", base]) == 0
    # unchanged scan → no baseline delta lines
    assert "baseline:" not in capsys.readouterr().err


@pytest.mark.integration
def test_markdown_format(fake_home, capsys) -> None:
    assert main(["scan", "--client", "cursor", "--format", "markdown", "--no-cost"]) == 0
    out = capsys.readouterr().out
    assert "### 🩺 MCP Checkup" in out
    assert "| toy" in out or "toy |" in out
    assert "\x1b[" not in out
