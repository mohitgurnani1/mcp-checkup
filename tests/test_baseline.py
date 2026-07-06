# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

from mcp_checkup.baseline import DEFAULT_BASELINE, compare, load, snapshot, write
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


def _error_entry(name: str) -> ScanEntry:
    spec = ServerSpec(name=name, transport=Transport.STDIO, command="python", args=[f"{name}.py"])
    d = Discovered(spec=spec, client="vscode", source="/fake/vscode.json")
    return ScanEntry(discovered=d, clients=["vscode"], error="boom")


def test_default_baseline_name() -> None:
    assert DEFAULT_BASELINE == ".mcp-checkup-baseline.json"


def test_snapshot_shape() -> None:
    report = ScanReport(entries=[_entry("toy", [_tool("alpha"), _tool("beta")])])
    snap = snapshot(report)
    assert snap["schema_version"] == 1
    server = snap["servers"]["toy"]
    assert server["total_anthropic"] > 0
    assert set(server["tools"]) == {"alpha", "beta"}
    tool = server["tools"]["alpha"]
    assert tool["tokens"] > 0
    assert len(tool["hash"]) == 64
    assert all(c in "0123456789abcdef" for c in tool["hash"])
    # total is the sum of per-tool anthropic tokens
    assert server["total_anthropic"] == sum(t["tokens"] for t in server["tools"].values())


def test_snapshot_skips_error_entries() -> None:
    report = ScanReport(entries=[_entry("toy", [_tool("a")]), _error_entry("dead")])
    assert set(snapshot(report)["servers"]) == {"toy"}


def test_snapshot_hash_is_stable_across_key_order() -> None:
    t1 = ToolInfo(name="a", description="d", input_schema={"x": 1, "y": 2})
    t2 = ToolInfo(name="a", description="d", input_schema={"y": 2, "x": 1})
    s1 = snapshot(ScanReport(entries=[_entry("srv", [t1])]))
    s2 = snapshot(ScanReport(entries=[_entry("srv", [t2])]))
    assert s1["servers"]["srv"]["tools"]["a"]["hash"] == s2["servers"]["srv"]["tools"]["a"]["hash"]


def test_write_load_round_trip(tmp_path) -> None:
    report = ScanReport(entries=[_entry("toy", [_tool("alpha")])])
    path = tmp_path / DEFAULT_BASELINE
    write(report, path)
    assert load(path) == snapshot(report)


def test_load_missing_and_corrupt(tmp_path) -> None:
    assert load(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{")
    assert load(bad) is None
    not_dict = tmp_path / "list.json"
    not_dict.write_text("[1, 2]")
    assert load(not_dict) is None


def test_compare_no_changes() -> None:
    report = ScanReport(entries=[_entry("toy", [_tool("alpha")])])
    assert compare(report, snapshot(report)) == []


def test_compare_detects_growth() -> None:
    before = ScanReport(entries=[_entry("toy", [_tool("alpha", "short")])])
    after = ScanReport(
        entries=[
            _entry(
                "toy",
                [_tool("alpha", "a much longer description with many extra words in it now")],
            )
        ]
    )
    lines = compare(after, snapshot(before))
    grow = [ln for ln in lines if "grew" in ln]
    assert len(grow) == 1
    assert "server 'toy' grew +" in grow[0]
    assert "anthropic tokens since baseline" in grow[0]
    assert "->" in grow[0]


def test_compare_detects_shrink() -> None:
    before = ScanReport(
        entries=[_entry("toy", [_tool("alpha", "a much longer description with extra words")])]
    )
    after = ScanReport(entries=[_entry("toy", [_tool("alpha", "short")])])
    lines = compare(after, snapshot(before))
    assert any("shrank" in ln and "-" in ln for ln in lines)


def test_compare_detects_new_server() -> None:
    before = ScanReport(entries=[_entry("toy", [_tool("a")])])
    after = ScanReport(entries=[_entry("toy", [_tool("a")]), _entry("fresh", [_tool("b")])])
    lines = compare(after, snapshot(before))
    assert len(lines) == 1
    assert lines[0].startswith("new server 'fresh' (")
    assert "tokens)" in lines[0]


def test_compare_detects_removed_server() -> None:
    before = ScanReport(entries=[_entry("toy", [_tool("a")]), _entry("gone", [_tool("b")])])
    after = ScanReport(entries=[_entry("toy", [_tool("a")])])
    lines = compare(after, snapshot(before))
    assert len(lines) == 1
    assert "removed server 'gone'" in lines[0]


def test_compare_detects_hash_change_with_equal_tokens() -> None:
    # Mutate only the pinned hash: token counts stay identical, so this is
    # exactly the description-swap case a token delta cannot catch.
    report = ScanReport(entries=[_entry("toy", [_tool("alpha")])])
    baseline = snapshot(report)
    baseline["servers"]["toy"]["tools"]["alpha"]["hash"] = "0" * 64
    lines = compare(report, baseline)
    assert lines == ["tool 'alpha' on 'toy' changed since baseline"]
