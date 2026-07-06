# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Trim proxy: a stdio MCP server that wraps another stdio MCP server.

The proxy connects to a child server once, then re-serves the child's
inventory on its own stdio with a *trimmed* ``tools/list`` (schemas
compressed via :mod:`mcp_checkup.compress`, optionally filtered to an
allow-list) while forwarding ``tools/call`` and the resource/prompt
endpoints through unchanged. Clients pay fewer context tokens for the
same tools.

Like :mod:`mcp_checkup.transport`, this module is a deliberate seam:
it is one of the only places outside test fixtures that imports the
``mcp`` SDK directly.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import shlex
import sys
import time
from typing import Any

import mcp.types as mcp_types
from mcp import ClientSession, McpError, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from .compress import CompressPolicy, compress_tool
from .models import ToolInfo
from .transport import _stderr_sink

SERVER_NAME = "mcp-checkup-proxy"

# Environment variables the proxy reacts to (documented for humans; the
# strings are used inline where read).
DEBUG_ENV = "MCP_CHECKUP_DEBUG"
PROXY_LOG_ENV = "MCP_CHECKUP_PROXY_LOG"


def _trim_tool(tool: mcp_types.Tool, policy: CompressPolicy) -> mcp_types.Tool:
    """Return a copy of *tool* with description and inputSchema compressed.

    Only the fields :func:`compress_tool` understands are touched; everything
    else (outputSchema, annotations, _meta, ...) passes through untouched.
    """
    info = ToolInfo(
        name=tool.name,
        description=tool.description or "",
        input_schema=tool.inputSchema,
    )
    compressed = compress_tool(info, policy)
    return tool.model_copy(
        update={
            "description": compressed.description or None,
            "inputSchema": compressed.input_schema,
        }
    )


def _log_call(tool: str, ok: bool, epoch: float, duration_s: float) -> None:
    """Emit per-call telemetry: stderr line under DEBUG, JSONL when configured."""
    if os.environ.get(DEBUG_ENV):
        print(
            f"[{SERVER_NAME}] tool={tool} ok={ok} duration_ms={duration_s * 1000:.1f}",
            file=sys.stderr,
        )
    path = os.environ.get(PROXY_LOG_ENV)
    if path:
        record = {"tool": tool, "ts_monotonic_delta": time.monotonic() - epoch, "ok": ok}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def build_proxy_server(
    child: ClientSession,
    child_caps: mcp_types.ServerCapabilities,
    *,
    trim: bool = True,
    allow_tools: list[str] | None = None,
    policy: CompressPolicy | None = None,
) -> Server:
    """Build the low-level MCP server that fronts an initialized *child* session.

    The returned server is transport-agnostic: :func:`run_proxy` runs it on
    real stdio, tests can run it over in-memory streams. The child session
    must stay open for as long as the server runs.
    """
    active_policy = policy if policy is not None else CompressPolicy()
    allowed = set(allow_tools) if allow_tools is not None else None
    server: Server = Server(SERVER_NAME)
    epoch = time.monotonic()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        result = await child.list_tools()
        tools = [t for t in result.tools if allowed is None or t.name in allowed]
        if not trim:
            return tools
        return [_trim_tool(t, active_policy) for t in tools]

    # validate_input=False: the child owns validation semantics; the proxy
    # must not reject anything the child would accept (we also serve
    # compressed schemas, so validating against them here would be redundant).
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> mcp_types.CallToolResult:
        start = time.monotonic()
        ok = False
        try:
            result = await child.call_tool(name, arguments)
            ok = not result.isError
            # Returning the child's CallToolResult verbatim makes the SDK
            # forward content blocks, structuredContent, and isError as-is.
            return result
        finally:
            _log_call(name, ok, epoch, time.monotonic() - start)

    @server.list_resources()
    async def list_resources() -> list[mcp_types.Resource]:
        if not child_caps.resources:
            return []
        try:
            return (await child.list_resources()).resources
        except McpError as exc:
            if exc.error.code == mcp_types.METHOD_NOT_FOUND:
                return []
            raise

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        result = await child.read_resource(uri)
        contents: list[ReadResourceContents] = []
        for item in result.contents:
            if isinstance(item, mcp_types.TextResourceContents):
                contents.append(ReadResourceContents(content=item.text, mime_type=item.mimeType))
            else:
                contents.append(
                    ReadResourceContents(
                        content=base64.b64decode(item.blob), mime_type=item.mimeType
                    )
                )
        return contents

    @server.list_prompts()
    async def list_prompts() -> list[mcp_types.Prompt]:
        if not child_caps.prompts:
            return []
        try:
            return (await child.list_prompts()).prompts
        except McpError as exc:
            if exc.error.code == mcp_types.METHOD_NOT_FOUND:
                return []
            raise

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> mcp_types.GetPromptResult:
        return await child.get_prompt(name, arguments)

    return server


async def run_proxy(
    child_command: str,
    trim: bool = True,
    allow_tools: list[str] | None = None,
    policy: CompressPolicy | None = None,
) -> None:
    """Serve a trimmed view of the stdio server started by *child_command*.

    Connects to the child once (session-long connection), then serves MCP on
    this process's own stdin/stdout until the client disconnects (stdin EOF)
    or the task is cancelled; either way the child is shut down cleanly by
    the context managers on the way out.
    """
    tokens = shlex.split(child_command)
    if not tokens:
        raise ValueError("empty child command")
    params = StdioServerParameters(command=tokens[0], args=tokens[1:])
    with _stderr_sink() as errlog:
        async with (
            stdio_client(params, errlog=errlog) as (child_read, child_write),
            ClientSession(child_read, child_write) as child,
        ):
            caps = (await child.initialize()).capabilities
            server = build_proxy_server(
                child, caps, trim=trim, allow_tools=allow_tools, policy=policy
            )
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, server.create_initialization_options())


def wrap_config(config: dict, policy_args: list[str] | None = None) -> dict:
    """Rewrite an ``mcpServers``-style config so every stdio server runs trimmed.

    Returns a deep copy of *config*; the input is never mutated. Each stdio
    entry (one with a ``command``) is rewritten to launch
    ``mcp-checkup serve --wrap "<original command>" --trim`` (plus any
    *policy_args*), with the original command and args re-joined into a
    single shell-quoted string via :func:`shlex.join`. The entry's ``env``
    is carried over when present. HTTP entries (no ``command``) and the
    top-level key (``mcpServers`` or ``servers``) are preserved unchanged.
    """
    out = copy.deepcopy(config)
    servers = out
    for key in ("mcpServers", "servers"):
        if isinstance(out.get(key), dict):
            servers = out[key]
            break
    for name, entry in servers.items():
        if not isinstance(entry, dict) or "command" not in entry:
            continue
        original = shlex.join([entry["command"], *entry.get("args", [])])
        wrapped: dict[str, Any] = {
            "command": "mcp-checkup",
            "args": ["serve", "--wrap", original, "--trim", *(policy_args or [])],
        }
        if "env" in entry:
            wrapped["env"] = entry["env"]
        servers[name] = wrapped
    return out
