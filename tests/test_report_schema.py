# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import jsonschema
import pytest

from mcp_checkup.checks.base import Finding, Severity
from mcp_checkup.discovery.base import Discovered
from mcp_checkup.models import ServerInventory, ServerSpec, ToolInfo, Transport
from mcp_checkup.render import scan_to_json
from mcp_checkup.scan import ScanEntry, ScanReport
from mcp_checkup.tokens import weigh_inventory

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "report.v1.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _report() -> ScanReport:
    spec = ServerSpec(name="toy", transport=Transport.STDIO, command="python", args=["toy.py"])
    inv = ServerInventory(
        spec=spec,
        tools=[
            ToolInfo(
                name="fetch",
                description="fetch a url",
                input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
            )
        ],
    )
    ok = ScanEntry(
        discovered=Discovered(spec=spec, client="cursor", source="/fake/cursor.json"),
        clients=["cursor", "claude-desktop"],
        result=weigh_inventory(inv),
    )
    dead_spec = ServerSpec(name="dead", transport=Transport.HTTP, url="https://x.example/mcp")
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
            detail="4,000 chars",
        ),
        Finding(
            check_id="S02",
            severity=Severity.LOW,
            server="toy",
            summary="server-level finding without a tool",
        ),
    ]
    return ScanReport(entries=[ok, dead], findings=findings)


def _doc() -> dict:
    return json.loads(scan_to_json(_report()))


def test_scan_json_validates() -> None:
    jsonschema.validate(instance=_doc(), schema=_schema())


def test_scan_json_with_costs_validates() -> None:
    # The CLI appends a costs array (render.costs_doc shape) to the scan doc.
    doc = _doc()
    doc["costs"] = [
        {
            "model": "claude-sonnet-4-5",
            "provider": "anthropic",
            "tokens": 1546,
            "usd_per_request": 0.004638,
            "usd_per_session": 0.04638,
            "turns": 10,
            "context_pct": 0.77,
        }
    ]
    jsonschema.validate(instance=doc, schema=_schema())


def test_schema_is_draft_2020_12() -> None:
    schema = _schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d["servers"][0].pop("name"),
        lambda d: d["servers"][0].update(transport="carrier-pigeon"),
        lambda d: d["findings"][0].update(severity="urgent"),
        lambda d: d.pop("totals"),
        lambda d: d.update(costs=[{"model": "gpt-4o"}]),
    ],
)
def test_mutated_doc_fails(mutate) -> None:
    doc = _doc()
    mutate(doc)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=doc, schema=_schema())
