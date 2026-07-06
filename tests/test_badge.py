# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from mcp_checkup.badge import badge_color, badge_doc, write_badge
from mcp_checkup.discovery.base import Discovered
from mcp_checkup.models import (
    ServerInventory,
    ServerSpec,
    ToolInfo,
    ToolWeight,
    Transport,
    WeighResult,
)
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


def _report_with_tokens(n: int) -> ScanReport:
    """Report whose anthropic total is exactly *n* (hand-built weights)."""
    spec = ServerSpec(name="srv", transport=Transport.STDIO, command="python")
    tool = _tool("t")
    inv = ServerInventory(spec=spec, tools=[tool])
    result = WeighResult(
        inventory=inv,
        tool_weights=[ToolWeight(tool=tool, tokens={"anthropic": n, "openai": n, "gemini": n})],
    )
    d = Discovered(spec=spec, client="cursor", source="/fake/cursor.json")
    return ScanReport(entries=[ScanEntry(discovered=d, clients=["cursor"], result=result)])


def test_badge_doc_schema() -> None:
    report = ScanReport(entries=[_entry("toy", [_tool("alpha")])])
    doc = badge_doc(report)
    assert set(doc) == {"schemaVersion", "label", "message", "color"}
    assert doc["schemaVersion"] == 1
    assert doc["label"] == "context tax"
    assert doc["message"].endswith(" tokens")
    # tiny fixture server is comfortably under the green threshold
    assert doc["color"] == "green"


@pytest.mark.parametrize(
    ("tokens", "color"),
    [
        (0, "green"),
        (4_999, "green"),
        (5_000, "yellow"),
        (19_999, "yellow"),
        (20_000, "orange"),
        (39_999, "orange"),
        (40_000, "red"),
        (123_456, "red"),
    ],
)
def test_color_thresholds(tokens: int, color: str) -> None:
    assert badge_color(tokens) == color
    assert badge_doc(_report_with_tokens(tokens))["color"] == color


def test_message_uses_thousands_separator() -> None:
    assert badge_doc(_report_with_tokens(12_345))["message"] == "12,345 tokens"


def test_empty_report_is_zero_green() -> None:
    doc = badge_doc(ScanReport(entries=[]))
    assert doc["message"] == "0 tokens"
    assert doc["color"] == "green"


def test_write_badge_round_trip(tmp_path) -> None:
    report = _report_with_tokens(21_000)
    path = tmp_path / "badge.json"
    write_badge(report, path)
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw) == badge_doc(report)
    assert json.loads(raw)["color"] == "orange"
