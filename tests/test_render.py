# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import json

from rich.console import Console

from mcp_checkup.models import (
    REPORT_SCHEMA_VERSION,
    ServerInventory,
    ServerSpec,
    ToolInfo,
    ToolWeight,
    Transport,
    WeighResult,
)
from mcp_checkup.render import print_table, to_json


def _result() -> WeighResult:
    spec = ServerSpec(name="toy", transport=Transport.STDIO, command="python")
    tool = ToolInfo(name="add", description="Add two integers.", input_schema={"type": "object"})
    inv = ServerInventory(spec=spec, tools=[tool])
    return WeighResult(
        inventory=inv,
        tool_weights=[ToolWeight(tool=tool, tokens={"anthropic": 30, "openai": 35, "gemini": 28})],
    )


def test_to_json_shape() -> None:
    doc = json.loads(to_json(_result()))
    assert doc["schema_version"] == REPORT_SCHEMA_VERSION
    assert doc["server"] == {"name": "toy", "transport": "stdio"}
    assert doc["tools"][0]["name"] == "add"
    assert doc["tools"][0]["tokens"]["openai"] == 35
    assert doc["totals"] == {"anthropic": 30, "openai": 35, "gemini": 28}


def test_print_table_renders() -> None:
    console = Console(record=True, width=100)
    print_table(_result(), console=console)
    out = console.export_text()
    assert "toy" in out
    assert "add" in out
    assert "Context tax" in out
