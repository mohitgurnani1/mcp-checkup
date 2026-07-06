# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Talk to MCP servers and collect their inventory.

This module is the only place in ``mcp_checkup`` (outside test fixtures)
that imports the ``mcp`` SDK. It is the deliberate seam for a future SDK
v2 migration: everything else codes against :mod:`mcp_checkup.models`.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any, TextIO
from urllib.parse import urlparse

import mcp.types as mcp_types
from mcp import ClientSession, McpError, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .models import (
    PromptInfo,
    ResourceInfo,
    ServerInventory,
    ServerSpec,
    ToolInfo,
    Transport,
)


class TransportError(Exception):
    """A server could not be reached, initialized, or inspected."""


def split_command(command_line: str) -> list[str]:
    """Split a command-line string, preserving Windows path backslashes.

    POSIX :func:`shlex.split` treats ``\\`` as an escape, which mangles
    ``C:\\...\\python.exe``; non-POSIX mode keeps backslashes but leaves
    surrounding quotes on tokens, so strip those.
    """
    if os.name == "nt":
        return [t.strip("\"'") for t in shlex.split(command_line, posix=False)]
    return shlex.split(command_line)


def parse_target(target: str) -> ServerSpec:
    """Turn a raw CLI target string into a :class:`ServerSpec`.

    ``http(s)://`` targets become HTTP specs named after the host; anything
    else is shell-split into a stdio command line, named after the last path
    component of the executable.
    """
    target = target.strip()
    if not target:
        raise ValueError("empty server target")
    if target.startswith(("http://", "https://")):
        host = urlparse(target).netloc
        return ServerSpec(name=host or target, transport=Transport.HTTP, url=target)
    tokens = split_command(target)
    if not tokens:
        raise ValueError("empty server target")
    command, *args = tokens
    # Last path component regardless of separator style (host OS agnostic).
    name = re.split(r"[\\/]", command.rstrip("/\\"))[-1] or command
    return ServerSpec(name=name, transport=Transport.STDIO, command=command, args=args)


async def fetch_inventory(spec: ServerSpec, timeout: float = 10.0) -> ServerInventory:
    """Connect to the server described by ``spec`` and list everything it offers.

    The whole exchange (connect, initialize, paginated listings) is bounded
    by ``timeout`` seconds. All failures are wrapped in :class:`TransportError`.
    """
    try:
        return await asyncio.wait_for(_fetch(spec), timeout)
    except TransportError:
        raise
    except asyncio.TimeoutError as exc:
        raise TransportError(f"MCP server {spec.name!r} timed out after {timeout:g}s") from exc
    except Exception as exc:
        raise TransportError(f"failed to inspect MCP server {spec.name!r}: {exc}") from exc


@contextmanager
def _stderr_sink() -> Iterator[TextIO]:
    """Yield a destination for the child server's stderr.

    Server log noise would pollute the report, so child stderr goes to devnull
    unless MCP_CHECKUP_DEBUG is set. ``stdio_client`` also requires the sink to
    have a real file descriptor, which ``sys.stderr`` lacks under pytest
    capture — another reason devnull is the default.
    """
    if os.environ.get("MCP_CHECKUP_DEBUG"):
        try:
            sys.stderr.fileno()
        except (OSError, ValueError, AttributeError):
            pass
        else:
            yield sys.stderr
            return
    with open(os.devnull, "w") as sink:
        yield sink


async def _fetch(spec: ServerSpec) -> ServerInventory:
    if spec.transport is Transport.STDIO:
        if not spec.command:
            raise TransportError(f"MCP server {spec.name!r}: stdio spec has no command")
        params = StdioServerParameters(
            command=spec.command,
            args=list(spec.args),
            # None means "inherit the SDK default environment"; merge any
            # spec-provided variables over it explicitly.
            env={**get_default_environment(), **spec.env} if spec.env else None,
        )
        with _stderr_sink() as errlog:
            async with (
                stdio_client(params, errlog=errlog) as (read, write),
                ClientSession(read, write) as session,
            ):
                return await inventory_from_session(session, spec)

    if not spec.url:
        raise TransportError(f"MCP server {spec.name!r}: http spec has no url")
    async with (
        streamablehttp_client(spec.url, headers=spec.headers or None) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        return await inventory_from_session(session, spec)


async def inventory_from_session(
    session: ClientSession, spec: ServerSpec, *, initialize: bool = True
) -> ServerInventory:
    """Build a :class:`ServerInventory` from an open client session.

    Pass ``initialize=False`` if the session has already been initialized
    (e.g. by the SDK's in-memory test helper). When capabilities are known,
    unadvertised listings are skipped; either way a "method not found" reply
    yields an empty list for that capability.
    """
    caps = (await session.initialize()).capabilities if initialize else None

    tools = await _collect(session.list_tools, "tools", supported=caps is None or caps.tools)
    resources = await _collect(
        session.list_resources, "resources", supported=caps is None or caps.resources
    )
    prompts = await _collect(
        session.list_prompts, "prompts", supported=caps is None or caps.prompts
    )

    return ServerInventory(
        spec=spec,
        tools=[
            ToolInfo(name=t.name, description=t.description or "", input_schema=t.inputSchema)
            for t in tools
        ],
        resources=[
            ResourceInfo(uri=str(r.uri), name=r.name, description=r.description or "")
            for r in resources
        ],
        prompts=[PromptInfo(name=p.name, description=p.description or "") for p in prompts],
    )


async def _collect(
    list_method: Callable[..., Awaitable[Any]], attr: str, *, supported: object
) -> list[Any]:
    """Drain one paginated ``list_*`` endpoint, following ``nextCursor``."""
    if not supported:
        return []
    items: list[Any] = []
    cursor: str | None = None
    while True:
        try:
            if cursor is None:
                result = await list_method()
            else:
                result = await list_method(params=mcp_types.PaginatedRequestParams(cursor=cursor))
        except McpError as exc:
            if exc.error.code == mcp_types.METHOD_NOT_FOUND:
                return []
            raise
        items.extend(getattr(result, attr))
        cursor = result.nextCursor
        if cursor is None:
            return items
