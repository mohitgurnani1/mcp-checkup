# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Check engine contract.

A check is a function ``(ctx: CheckContext) -> list[Finding]`` registered via
``@check(id, severity)``. Checks are heuristics: read-only, client-side, and
must never raise — a broken check yields no findings, not a crash.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from mcp_checkup.models import ServerInventory


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Finding:
    check_id: str  # e.g. "W01"
    severity: Severity
    server: str
    summary: str  # one line, shown in the table
    detail: str = ""  # shown with --verbose
    tool: str | None = None  # tool name if tool-scoped


@dataclass
class CheckContext:
    """Everything checks may inspect: one server plus the full scan for
    cross-server rules (duplicates, shadowing)."""

    inventory: ServerInventory
    all_inventories: list[ServerInventory] = field(default_factory=list)


CheckFn = Callable[[CheckContext], list[Finding]]


@dataclass
class _Registered:
    id: str
    severity: Severity
    fn: CheckFn
    description: str


CHECKS: dict[str, _Registered] = {}


def check(check_id: str, severity: Severity, description: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        CHECKS[check_id] = _Registered(
            id=check_id, severity=severity, fn=fn, description=description
        )
        return fn

    return deco


def run_checks(
    inventories: list[ServerInventory], disabled: set[str] | None = None
) -> list[Finding]:
    """Run every registered check against every server. Never raises."""
    # Import rule modules lazily so registration happens on first use.
    from mcp_checkup.checks import security, weight  # noqa: F401

    disabled = disabled or set()
    findings: list[Finding] = []
    for inv in inventories:
        ctx = CheckContext(inventory=inv, all_inventories=inventories)
        for reg in CHECKS.values():
            if reg.id in disabled:
                continue
            try:
                findings.extend(reg.fn(ctx))
            except Exception:  # pragma: no cover - defensive: a check must not kill the scan
                continue
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings.sort(key=lambda f: (order[f.severity], f.check_id, f.server))
    return findings
