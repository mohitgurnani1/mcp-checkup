# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Weight checks (W01-W05): heuristics for token-heavy tool inventories.

Each check flags a way a server's advertised surface inflates the context
window: bloated schemas, oversized descriptions, enum explosions, too many
tools, and duplicate tool names across servers.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from mcp_checkup.checks.base import CheckContext, Finding, Severity, check
from mcp_checkup.serialize import serialize
from mcp_checkup.tokens import count_tokens

# W01: flag when the wire schema is this many times its minimal equivalent...
BLOAT_RATIO_THRESHOLD = 3.0
# ...but only when the tool is heavy enough for the bloat to matter.
BLOAT_MIN_ACTUAL_TOKENS = 300

# W02: a single tool description larger than this is doing a prompt's job.
DESCRIPTION_TOKEN_THRESHOLD = 1000

# W03: enums larger than this in the schema are a data table, not a schema.
ENUM_EXPLOSION_THRESHOLD = 50

# W04: models degrade selecting from tool lists larger than this.
TOOL_COUNT_THRESHOLD = 30

# minimal_schema: enums longer than this carry no structural signal and are dropped.
_MINIMAL_ENUM_MAX = 10

# Keys that are documentation, not structure; stripped by minimal_schema.
_STRIP_KEYS = frozenset({"description", "title", "examples", "default", "$comment", "$schema"})


def _minimize(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _STRIP_KEYS:
                continue
            if key == "enum" and isinstance(value, list) and len(value) > _MINIMAL_ENUM_MAX:
                # An oversized enum is dropped entirely; the sibling "type" is kept.
                continue
            out[key] = _minimize(value)
        return out
    if isinstance(node, list):
        return [_minimize(item) for item in node]
    return node


def minimal_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return *schema* reduced to its structural minimum.

    Recursively strips documentation keys (description/title/examples/
    default/$comment/$schema) and drops enums longer than
    :data:`_MINIMAL_ENUM_MAX` entries, while preserving the
    type/properties/required/items structure. Pure: *schema* is never
    mutated; a new dict is returned.
    """
    return _minimize(schema)


@check("W01", Severity.MEDIUM, "Tool schema much larger than its minimal equivalent")
def schema_bloat(ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for tool in ctx.inventory.tools:
        tokens_actual = count_tokens(serialize(tool, "anthropic"))
        if tokens_actual <= BLOAT_MIN_ACTUAL_TOKENS:
            continue
        minimal_tool = replace(tool, input_schema=minimal_schema(tool.input_schema))
        tokens_minimal = count_tokens(serialize(minimal_tool, "anthropic"))
        if tokens_minimal <= 0:
            continue
        ratio = tokens_actual / tokens_minimal
        if ratio > BLOAT_RATIO_THRESHOLD:
            findings.append(
                Finding(
                    check_id="W01",
                    severity=Severity.MEDIUM,
                    server=ctx.inventory.spec.name,
                    tool=tool.name,
                    summary=(
                        f"tool '{tool.name}' is {ratio:.1f}x its minimal schema "
                        f"({tokens_actual} vs {tokens_minimal} tokens)"
                    ),
                    detail=(
                        "The tool definition spends most of its tokens on descriptions, "
                        "titles, examples, defaults, or oversized enums rather than on "
                        "schema structure. Trimming them reduces the per-request context tax."
                    ),
                )
            )
    return findings


@check("W02", Severity.LOW, "Oversized tool description")
def oversized_description(ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for tool in ctx.inventory.tools:
        tokens = count_tokens(tool.description)
        if tokens > DESCRIPTION_TOKEN_THRESHOLD:
            findings.append(
                Finding(
                    check_id="W02",
                    severity=Severity.LOW,
                    server=ctx.inventory.spec.name,
                    tool=tool.name,
                    summary=(
                        f"tool '{tool.name}' description is {tokens} tokens "
                        f"(> {DESCRIPTION_TOKEN_THRESHOLD})"
                    ),
                    detail=(
                        "The description alone exceeds the threshold; it is paid on every "
                        "request that includes this tool. Consider moving reference material "
                        "into a resource or prompt."
                    ),
                )
            )
    return findings


def _walk_enums(node: Any, path: str) -> Iterator[tuple[str, int]]:
    """Yield (property path, enum length) for every enum in *node* over the threshold."""
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list) and len(enum) > ENUM_EXPLOSION_THRESHOLD:
            yield (path or "(root)", len(enum))
        for key, value in node.items():
            yield from _walk_enums(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk_enums(item, f"{path}[{i}]")


@check("W03", Severity.LOW, "Enum explosion")
def enum_explosion(ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for tool in ctx.inventory.tools:
        for path, length in _walk_enums(tool.input_schema, ""):
            findings.append(
                Finding(
                    check_id="W03",
                    severity=Severity.LOW,
                    server=ctx.inventory.spec.name,
                    tool=tool.name,
                    summary=(
                        f"tool '{tool.name}' has a {length}-entry enum at {path} "
                        f"(> {ENUM_EXPLOSION_THRESHOLD})"
                    ),
                    detail=(
                        "Enums this large are a data table embedded in the schema. Accept a "
                        "free-form string and validate server-side, or expose the values as "
                        "a resource."
                    ),
                )
            )
    return findings


@check("W04", Severity.LOW, "Tool count explosion")
def tool_count_explosion(ctx: CheckContext) -> list[Finding]:
    count = len(ctx.inventory.tools)
    if count <= TOOL_COUNT_THRESHOLD:
        return []
    return [
        Finding(
            check_id="W04",
            severity=Severity.LOW,
            server=ctx.inventory.spec.name,
            summary=f"server exposes {count} tools; models degrade with large tool lists",
            detail=(
                "Every advertised tool costs context on every request and dilutes the "
                "model's tool-selection accuracy. Split the server or gate tools behind "
                "a search/namespace mechanism."
            ),
        )
    ]


@check("W05", Severity.LOW, "Duplicate tool names across servers")
def duplicate_tool_names(ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for tool in ctx.inventory.tools:
        if tool.name in seen:
            continue
        seen.add(tool.name)
        holders = [
            inv for inv in ctx.all_inventories if any(t.name == tool.name for t in inv.tools)
        ]
        # Emit once per duplicated name, on the first server that advertises it.
        if len(holders) < 2 or holders[0] is not ctx.inventory:
            continue
        server_names = ", ".join(inv.spec.name for inv in holders)
        findings.append(
            Finding(
                check_id="W05",
                severity=Severity.LOW,
                server=ctx.inventory.spec.name,
                tool=tool.name,
                summary=(
                    f"tool '{tool.name}' is advertised by {len(holders)} servers: {server_names}"
                ),
                detail=(
                    "Duplicate tool names force clients to disambiguate (or silently "
                    "shadow one another), and the model may call the wrong server's tool."
                ),
            )
        )
    return findings
