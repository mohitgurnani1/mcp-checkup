# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import json
import sys

import pytest

from mcp_checkup import __version__
from mcp_checkup.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "weigh" in capsys.readouterr().out


def test_weigh_requires_target(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["weigh"])


def test_weigh_unreachable_returns_3(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["weigh", "--timeout", "2", f"{sys.executable} -c pass"]) == 3
    assert "error:" in capsys.readouterr().err


@pytest.mark.integration
def test_weigh_toy_server_e2e(capsys: pytest.CaptureFixture[str]) -> None:
    target = f"{sys.executable} tests/fixtures/toy_server.py"
    assert main(["weigh", "--json", target]) == 0
    doc = json.loads(capsys.readouterr().out)
    names = {t["name"] for t in doc["tools"]}
    assert {"add", "greet", "search"} <= names
    assert doc["totals"]["anthropic"] > 0


@pytest.mark.integration
def test_weigh_config_file(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
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
    assert main(["weigh", "--config", str(cfg), "--server", "toy", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["server"]["name"] == "toy"
