# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import pytest

from mcp_checkup import __version__
from mcp_checkup.cli import main


def test_main_prints_banner_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "mcp-checkup" in out
    assert "WEIGHT" in out
    assert "HYGIENE" in out


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out
