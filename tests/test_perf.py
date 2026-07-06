# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Performance budget: a five-server scan must finish well under CI patience."""

import asyncio
import json
import sys
import time

import pytest

from mcp_checkup.scan import run_scan


@pytest.mark.integration
def test_five_server_scan_under_budget(tmp_path) -> None:
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    # Distinct trailing arg per server so dedupe keeps all five entries
    # (toy_server ignores extra argv).
    servers = {
        f"toy{i}": {
            "command": sys.executable,
            "args": ["tests/fixtures/toy_server.py", f"--instance={i}"],
        }
        for i in range(5)
    }
    (cursor / "mcp.json").write_text(json.dumps({"mcpServers": servers}))

    start = time.monotonic()
    report = asyncio.run(run_scan(home=tmp_path, clients=["cursor"], timeout=20))
    elapsed = time.monotonic() - start

    assert len(report.entries) == 5
    assert all(e.result for e in report.entries)
    assert elapsed < 10.0, f"scan took {elapsed:.1f}s (budget 10s)"
