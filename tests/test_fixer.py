# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the fix reporting and artifact emission (fixer.py)."""

import json

from rich.console import Console

from mcp_checkup.compress import CompressPolicy, compress_schema
from mcp_checkup.fixer import build_report, emit_sidecars, pr_text, render_fix_table
from mcp_checkup.models import ServerInventory, ServerSpec, ToolInfo, Transport

LONG_PROSE = (
    "Search the corpus for matching documents. The pipeline tokenizes the query, matches "
    "against an inverted index, blends lexical and semantic scores, and re-ranks with a "
    "cascade of models. Results can be filtered, grouped, deduplicated, and paginated."
)

BLOATED_TOOL = ToolInfo(
    name="search",
    description=LONG_PROSE,
    input_schema={
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Search input",
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The free-text query to run. Long queries are truncated.",
                "examples": ["hello"],
            },
            "region": {
                "type": "string",
                "description": "Region code. Determines the shard set queried.",
                "enum": [f"region-{i:02d}" for i in range(25)],
            },
        },
        "required": ["query"],
    },
)

LEAN_TOOL = ToolInfo(
    name="add",
    description="Add two integers.",
    input_schema={
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    },
)


def _inventory(tools=None) -> ServerInventory:
    return ServerInventory(
        spec=ServerSpec(name="toy", transport=Transport.STDIO, command="toy"),
        tools=[BLOATED_TOOL, LEAN_TOOL] if tools is None else tools,
    )


# --- build_report -------------------------------------------------------------


def test_build_report_totals_are_sum_of_rows():
    report = build_report(_inventory(), CompressPolicy())
    assert [r.name for r in report.rows] == ["search", "add"]
    assert report.total_before == sum(r.before for r in report.rows)
    assert report.total_after == sum(r.after for r in report.rows)
    assert report.total_saved == report.total_before - report.total_after
    assert report.server == "toy"


def test_build_report_pct_saved():
    report = build_report(_inventory(), CompressPolicy())
    expected = 100.0 * (report.total_before - report.total_after) / report.total_before
    assert report.pct_saved == expected
    assert 0.0 < report.pct_saved < 100.0


def test_build_report_empty_inventory_has_zero_pct_saved():
    report = build_report(_inventory(tools=[]), CompressPolicy())
    assert report.rows == []
    assert report.total_before == 0
    assert report.pct_saved == 0.0


# --- emit_sidecars --------------------------------------------------------------


def test_emit_sidecars_writes_schema_per_tool_plus_tools_md(tmp_path):
    inv = _inventory()
    policy = CompressPolicy()
    paths = emit_sidecars(inv, policy, tmp_path)

    assert len(paths) == len(inv.tools) + 1
    for path in paths:
        assert path.exists()

    for tool in inv.tools:
        sidecar = tmp_path / f"toy.{tool.name}.schema.json"
        assert sidecar in paths
        assert json.loads(sidecar.read_text()) == compress_schema(tool.input_schema, policy)

    tools_md = (tmp_path / "TOOLS.md").read_text()
    assert paths[-1] == tmp_path / "TOOLS.md"
    for tool in inv.tools:
        assert tool.name in tools_md
    assert "drop-in" in tools_md


def test_emit_sidecars_creates_out_dir(tmp_path):
    out_dir = tmp_path / "nested" / "sidecars"
    paths = emit_sidecars(_inventory(), CompressPolicy(), out_dir)
    assert out_dir.is_dir()
    assert all(p.parent == out_dir for p in paths)


# --- pr_text ----------------------------------------------------------------------


def test_pr_text_contains_per_tool_numbers_and_links():
    inv = _inventory()
    report = build_report(inv, CompressPolicy())
    text = pr_text(inv, report)

    for row in report.rows:
        assert f"| {row.name} | {row.before} | {row.after} | {row.saved} |" in text
    assert str(report.total_before) in text
    assert str(report.total_after) in text
    assert "https://github.com/mohitgurnani1/mcp-checkup" in text
    assert "2808" in text
    assert "o200k_base" in text  # measurement method is disclosed
    assert "\x1b" not in text  # no ANSI escapes


def test_pr_text_links_are_reference_style_at_bottom():
    inv = _inventory()
    text = pr_text(inv, build_report(inv, CompressPolicy()))
    body, *_ = text.partition("[1]:")
    assert "](http" not in body  # no inline markdown links mid-sentence
    assert text.rstrip().splitlines()[-2].startswith("[1]: ")
    assert text.rstrip().splitlines()[-1].startswith("[2]: ")


# --- render_fix_table ----------------------------------------------------------------


def test_render_fix_table_shows_rows_totals_and_honesty_line():
    report = build_report(_inventory(), CompressPolicy())
    console = Console(record=True, width=120)
    render_fix_table(report, console)
    out = console.export_text()

    for row in report.rows:
        assert row.name in out
    assert "Total" in out
    assert f"% saved: {report.pct_saved:.1f}%" in out
    assert "trim proxy (v0.7)" in out
