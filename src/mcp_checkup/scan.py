# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Scan: discover all configured MCP servers and weigh them concurrently."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from mcp_checkup.discovery import Discovered, discover_all
from mcp_checkup.models import WeighResult
from mcp_checkup.tokens import weigh_inventory
from mcp_checkup.transport import TransportError, fetch_inventory


@dataclass
class ScanEntry:
    """Outcome for one discovered server: a result or an error."""

    discovered: Discovered
    clients: list[str] = field(default_factory=list)  # all clients referencing it
    result: WeighResult | None = None
    error: str | None = None


@dataclass
class ScanReport:
    entries: list[ScanEntry] = field(default_factory=list)

    def totals(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries:
            if e.result:
                for provider, n in e.result.totals().items():
                    out[provider] = out.get(provider, 0) + n
        return out

    @property
    def tool_count(self) -> int:
        return sum(len(e.result.tool_weights) for e in self.entries if e.result)


def dedupe(found: list[Discovered]) -> list[ScanEntry]:
    """Merge servers referenced by several clients into one entry each."""
    by_key: dict[tuple, ScanEntry] = {}
    for d in found:
        key = d.identity()
        if key in by_key:
            entry = by_key[key]
            if d.client not in entry.clients:
                entry.clients.append(d.client)
        else:
            by_key[key] = ScanEntry(discovered=d, clients=[d.client], error=d.error)
    return list(by_key.values())


async def _weigh_entry(entry: ScanEntry, timeout: float) -> None:
    if entry.error:  # e.g. needs-input — don't attempt connection
        return
    try:
        inventory = await fetch_inventory(entry.discovered.spec, timeout=timeout)
        entry.result = weigh_inventory(inventory)
    except TransportError as exc:
        entry.error = str(exc)


async def run_scan(
    home: Path | None = None,
    clients: list[str] | None = None,
    timeout: float = 10.0,
    concurrency: int = 8,
) -> ScanReport:
    entries = dedupe(discover_all(home=home, clients=clients))
    sem = asyncio.Semaphore(concurrency)

    async def bounded(entry: ScanEntry) -> None:
        async with sem:
            await _weigh_entry(entry, timeout)

    await asyncio.gather(*(bounded(e) for e in entries))
    return ScanReport(entries=entries)
