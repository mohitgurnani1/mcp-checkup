# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Security hygiene checks (H01-H04).

Read-only, defensive heuristics over inventories the scan already fetched:
pattern matching on configured server specs and advertised tool descriptions.
No network probing, no exploitation attempts.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from mcp_checkup.checks.base import CheckContext, Finding, Severity, check
from mcp_checkup.models import ServerInventory, Transport

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Header keys that suggest some client credential is configured (case-insensitive substrings).
_AUTH_KEY_HINTS = ("authorization", "api-key", "x-api-key", "token")

# Tool-poisoning heuristics (H02). One entry per pattern family; a matching tool's
# finding lists every family that hit. Kept module-level so the corpus can grow.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "hidden-instructions",
        re.compile(r"<\s*/?\s*(?:important|secret|system)\s*>|\[\s*system\s*\]", re.IGNORECASE),
    ),
    (
        "concealment",
        re.compile(
            r"do\s+not\s+tell\s+the\s+user|don.?t\s+mention|do\s+not\s+inform|hide\s+this\s+from",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction-override",
        re.compile(r"ignore\s+(?:all\s+)?previous(?:\s+instructions)?", re.IGNORECASE),
    ),
    (
        "sensitive-path",
        re.compile(
            r"~/\.ssh|\bid_rsa\b|\.env\b|\.aws/credentials|/etc/passwd",
            re.IGNORECASE,
        ),
    ),
    (
        "before-using-read",
        re.compile(r"before\s+using\s+this\s+tool[\s,:;-]*read", re.IGNORECASE),
    ),
]

# Cross-server reference heuristics (H03).
_MIN_REFERENCED_NAME_LEN = 5
_BEHAVIORAL_RE = re.compile(
    r"instead\s+of|always\s+use|when\s+using|before\s+calling|after\s+calling|\boverride\b",
    re.IGNORECASE,
)

# Capability buckets (H04). Matched as whole words after normalizing separators,
# so "run_command" matches "run_command" or "run command", while "exec" does not
# match "executive".
_WRITE_EXEC_KEYWORDS = (
    "write",
    "delete",
    "execute",
    "exec",
    "run_command",
    "shell",
    "create_file",
    "move",
    "remove",
)
_FETCH_KEYWORDS = ("fetch", "http", "download", "url", "request", "browse", "web")


def _normalize(text: str) -> str:
    """Lowercase and collapse separators so snake_case names match as words."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower())


def _keyword_pattern(keywords: tuple[str, ...]) -> re.Pattern[str]:
    alts = "|".join(re.escape(_normalize(kw).strip()) for kw in keywords)
    return re.compile(rf"(?<![a-z0-9])(?:{alts})(?![a-z0-9])")


_WRITE_EXEC_RE = _keyword_pattern(_WRITE_EXEC_KEYWORDS)
_FETCH_RE = _keyword_pattern(_FETCH_KEYWORDS)


@check("H01", Severity.HIGH, "Remote MCP server configured without authentication")
def check_remote_without_auth(ctx: CheckContext) -> list[Finding]:
    spec = ctx.inventory.spec
    if spec.transport is not Transport.HTTP or not spec.url:
        return []
    host = (urlparse(spec.url).hostname or "").lower()
    if not host or host in _LOCAL_HOSTS:
        return []
    if any(hint in key.lower() for key in spec.headers for hint in _AUTH_KEY_HINTS):
        return []
    return [
        Finding(
            check_id="H01",
            severity=Severity.HIGH,
            server=spec.name,
            summary=f"Remote server at {host} is reachable with no client auth configured",
            detail=(
                "This server's inventory was fetched over HTTP and its configuration "
                "carries no auth-looking header (authorization / api-key / x-api-key / "
                "token). The server may authenticate other ways (mTLS, network "
                "allowlists, OAuth handshake); this flags a configured-without-"
                "credentials remote listing, not a proven open endpoint."
            ),
        )
    ]


@check("H02", Severity.HIGH, "Possible tool-poisoning language in description")
def check_tool_poisoning(ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for tool in ctx.inventory.tools:
        description = tool.description or ""
        hits = [name for name, pattern in PATTERNS if pattern.search(description)]
        if not hits:
            continue
        findings.append(
            Finding(
                check_id="H02",
                severity=Severity.HIGH,
                server=ctx.inventory.spec.name,
                summary=(
                    f"Tool '{tool.name}' description matches poisoning patterns: {', '.join(hits)}"
                ),
                detail=(
                    "Heuristic pattern match over the advertised description; review the "
                    "full text before trusting or removing the tool."
                ),
                tool=tool.name,
            )
        )
    return findings


@check("H03", Severity.MEDIUM, "Tool description references other servers' tools")
def check_cross_server_reference(ctx: CheckContext) -> list[Finding]:
    foreign: list[tuple[str, str, re.Pattern[str]]] = []
    for inv in ctx.all_inventories:
        if inv is ctx.inventory:
            continue
        for other in inv.tools:
            if len(other.name) < _MIN_REFERENCED_NAME_LEN:
                continue  # too generic to reference reliably (e.g. "add")
            name_re = re.compile(rf"(?<![\w-]){re.escape(other.name)}(?![\w-])", re.IGNORECASE)
            foreign.append((inv.spec.name, other.name, name_re))
    if not foreign:
        return []

    findings: list[Finding] = []
    for tool in ctx.inventory.tools:
        description = tool.description or ""
        if not _BEHAVIORAL_RE.search(description):
            continue
        for other_server, other_name, name_re in foreign:
            if not name_re.search(description):
                continue
            findings.append(
                Finding(
                    check_id="H03",
                    severity=Severity.MEDIUM,
                    server=ctx.inventory.spec.name,
                    summary=(
                        f"Tool '{tool.name}' references tool '{other_name}' from server "
                        f"'{other_server}' with behavioral language"
                    ),
                    detail=(
                        "A tool description that steers how another server's tool is used "
                        "is a shadowing heuristic; verify the description is legitimate."
                    ),
                    tool=tool.name,
                )
            )
    return findings


@check("H04", Severity.MEDIUM, "Write/exec tools alongside network-fetch tools")
def check_write_exec_with_fetch(ctx: CheckContext) -> list[Finding]:
    inventories: list[ServerInventory] = ctx.all_inventories or [ctx.inventory]
    if ctx.inventory is not inventories[0]:
        return []  # session-wide check: report once, on the first inventory

    write_exec: list[str] = []
    fetch: list[str] = []
    for inv in inventories:
        for tool in inv.tools:
            text = _normalize(f"{tool.name} {tool.description or ''}")
            label = f"{inv.spec.name}:{tool.name}"
            if _WRITE_EXEC_RE.search(text):
                write_exec.append(label)
            if _FETCH_RE.search(text):
                fetch.append(label)
    if not write_exec or not fetch:
        return []
    return [
        Finding(
            check_id="H04",
            severity=Severity.MEDIUM,
            server=ctx.inventory.spec.name,
            summary=(
                f"Session mixes write/exec tools (e.g. {', '.join(write_exec[:3])}) with "
                f"network-fetch tools (e.g. {', '.join(fetch[:3])})"
            ),
            detail=(
                "Exfiltration-chain heuristic (clearly labeled as such): all listed "
                "servers share one model context, so a fetch tool that ingests untrusted "
                "content sits alongside tools that can write files or execute commands. "
                "This is a capability-combination warning, not evidence of compromise."
            ),
        )
    ]
