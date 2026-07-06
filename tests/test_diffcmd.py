# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import copy

from rich.console import Console

from mcp_checkup.baseline import snapshot
from mcp_checkup.diffcmd import diff_baselines, render_diff
from mcp_checkup.discovery.base import Discovered
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
    spec = ServerSpec(name=name, transport=Transport.STDIO, command="python", args=[f"{name}.py"])
    d = Discovered(spec=spec, client=client, source=f"/fake/{client}.json")
    inv = ServerInventory(spec=spec, tools=tools)
    return ScanEntry(discovered=d, clients=[client], result=weigh_inventory(inv))


def _snap(*entries: ScanEntry) -> dict:
    return snapshot(ScanReport(entries=list(entries)))


def test_identical_baselines_yield_no_lines() -> None:
    snap = _snap(_entry("toy", [_tool("alpha")]))
    assert diff_baselines(snap, copy.deepcopy(snap)) == []


def test_grew() -> None:
    old = _snap(_entry("toy", [_tool("alpha", "short")]))
    new = _snap(
        _entry("toy", [_tool("alpha", "a much longer description with many extra words now")])
    )
    lines = diff_baselines(old, new)
    grow = [ln for ln in lines if "grew" in ln]
    assert len(grow) == 1
    assert "server 'toy' grew +" in grow[0]
    assert "anthropic tokens" in grow[0]
    assert "->" in grow[0]
    # description change also flips the pinned hash
    assert "tool 'alpha' on 'toy' definition changed" in lines


def test_shrank() -> None:
    old = _snap(_entry("toy", [_tool("alpha", "a much longer description with extra words")]))
    new = _snap(_entry("toy", [_tool("alpha", "short")]))
    lines = diff_baselines(old, new)
    assert any("server 'toy' shrank -" in ln for ln in lines)


def test_added_and_removed_servers() -> None:
    old = _snap(_entry("toy", [_tool("a")]), _entry("gone", [_tool("b")]))
    new = _snap(_entry("toy", [_tool("a")]), _entry("fresh", [_tool("c")]))
    lines = diff_baselines(old, new)
    assert len(lines) == 2
    assert lines[0].startswith("new server 'fresh' (")
    assert lines[0].endswith("tokens)")
    assert lines[1].startswith("removed server 'gone' (was ")


def test_added_and_removed_tools() -> None:
    old = _snap(_entry("toy", [_tool("alpha"), _tool("gone")]))
    new = _snap(_entry("toy", [_tool("alpha"), _tool("fresh")]))
    lines = diff_baselines(old, new)
    assert any(ln.startswith("new tool 'fresh' on 'toy' (") for ln in lines)
    assert "removed tool 'gone' on 'toy'" in lines


def test_hash_change_with_equal_tokens() -> None:
    old = _snap(_entry("toy", [_tool("alpha")]))
    new = copy.deepcopy(old)
    new["servers"]["toy"]["tools"]["alpha"]["hash"] = "0" * 64
    assert diff_baselines(old, new) == ["tool 'alpha' on 'toy' definition changed"]


def test_ordering_is_deterministic_and_sorted() -> None:
    old = _snap(_entry("zeta", [_tool("a")]), _entry("alpha", [_tool("a")]))
    # build "new" with reversed insertion order and extra drift on both servers
    new = _snap(
        _entry("alpha", [_tool("a"), _tool("b")]),
        _entry("zeta", [_tool("a"), _tool("b")]),
    )
    lines = diff_baselines(old, new)
    assert lines == diff_baselines(old, new)  # stable across calls
    alpha_lines = [i for i, ln in enumerate(lines) if "'alpha'" in ln]
    zeta_lines = [i for i, ln in enumerate(lines) if "'zeta'" in ln]
    assert max(alpha_lines) < min(zeta_lines)  # servers sorted by name


def test_render_diff_prints_each_line_once() -> None:
    lines = [
        "new server 'fresh' (10 tokens)",
        "server 'toy' grew +5 anthropic tokens (10 -> 15)",
        "server 'toy2' shrank -5 anthropic tokens (15 -> 10)",
        "removed server 'gone' (was 10 tokens)",
        "removed tool 'x' on 'toy'",
        "tool 'alpha' on 'toy' definition changed",
    ]
    console = Console(record=True, width=120)
    render_diff(lines, console)
    out = console.export_text()
    for line in lines:
        assert line in out
    assert len(out.strip().splitlines()) == len(lines)


def test_render_diff_empty_prints_nothing() -> None:
    console = Console(record=True, width=120)
    render_diff([], console)
    assert console.export_text().strip() == ""
