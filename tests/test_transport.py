# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the MCP SDK transport layer."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import METHOD_NOT_FOUND, ErrorData

from mcp_checkup.models import ServerSpec, Transport
from mcp_checkup.transport import (
    TransportError,
    _collect,
    fetch_inventory,
    inventory_from_session,
    parse_target,
)

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from toy_server import mcp as toy_server

# --- parse_target -----------------------------------------------------------


def test_parse_target_http_url():
    spec = parse_target("https://example.com/mcp")
    assert spec.transport is Transport.HTTP
    assert spec.name == "example.com"
    assert spec.url == "https://example.com/mcp"
    assert spec.command is None


def test_parse_target_stdio_command_with_args_and_quotes():
    spec = parse_target("/usr/local/bin/my-server --flag 'a b' c")
    assert spec.transport is Transport.STDIO
    assert spec.name == "my-server"
    assert spec.command == "/usr/local/bin/my-server"
    assert spec.args == ["--flag", "a b", "c"]
    assert spec.url is None


def test_parse_target_bare_command():
    spec = parse_target("uvx some-mcp-server")
    assert spec.transport is Transport.STDIO
    assert spec.name == "uvx"
    assert spec.args == ["some-mcp-server"]


@pytest.mark.parametrize("target", ["", "   "])
def test_parse_target_empty_raises(target):
    with pytest.raises(ValueError):
        parse_target(target)


# --- in-memory integration against the toy server ---------------------------


def _fetch_toy_inventory():
    spec = ServerSpec(name="toy", transport=Transport.STDIO, command="unused")

    async def run():
        async with create_connected_server_and_client_session(toy_server) as session:
            # The helper already initialized the session.
            return await inventory_from_session(session, spec, initialize=False)

    return asyncio.run(run())


def test_in_memory_inventory():
    inventory = _fetch_toy_inventory()

    assert inventory.spec.name == "toy"
    assert {t.name for t in inventory.tools} == {"add", "greet", "search"}

    add = next(t for t in inventory.tools if t.name == "add")
    assert add.description == "Add two integers."
    assert isinstance(add.input_schema, dict)

    assert len(inventory.resources) == 1
    assert inventory.resources[0].uri == "toy://readme"
    assert inventory.resources[0].name == "readme"

    assert len(inventory.prompts) == 1
    assert inventory.prompts[0].name == "hello"


def test_in_memory_bloated_tool_schema():
    inventory = _fetch_toy_inventory()

    search = next(t for t in inventory.tools if t.name == "search")
    assert isinstance(search.input_schema, dict)
    properties = search.input_schema["properties"]
    assert "query" in properties
    assert len(properties) >= 10
    assert len(search.description.split()) >= 300


# --- pagination and capability edge cases ------------------------------------


def test_collect_follows_next_cursor():
    pages = {
        None: SimpleNamespace(tools=["t1", "t2"], nextCursor="page-2"),
        "page-2": SimpleNamespace(tools=["t3"], nextCursor=None),
    }

    async def list_tools(params=None):
        return pages[params.cursor if params else None]

    items = asyncio.run(_collect(list_tools, "tools", supported=True))
    assert items == ["t1", "t2", "t3"]


def test_collect_method_not_found_returns_empty():
    async def list_prompts(params=None):
        raise McpError(ErrorData(code=METHOD_NOT_FOUND, message="Method not found"))

    items = asyncio.run(_collect(list_prompts, "prompts", supported=True))
    assert items == []


def test_collect_skips_unsupported_capability():
    async def must_not_be_called(params=None):  # pragma: no cover
        raise AssertionError("should not be called")

    items = asyncio.run(_collect(must_not_be_called, "resources", supported=None))
    assert items == []


# --- timeout path ------------------------------------------------------------


@pytest.mark.integration
def test_fetch_inventory_http_connection_refused():
    # Port 1 is essentially never listening; connection is refused immediately.
    spec = ServerSpec(name="nohost", transport=Transport.HTTP, url="http://127.0.0.1:1/mcp")
    with pytest.raises(TransportError) as excinfo:
        asyncio.run(fetch_inventory(spec, timeout=5.0))
    assert "nohost" in str(excinfo.value)


@pytest.mark.integration
def test_fetch_inventory_timeout():
    spec = ServerSpec(
        name="sleepy",
        transport=Transport.STDIO,
        command=sys.executable,
        args=["-c", "import time; time.sleep(60)"],
    )
    with pytest.raises(TransportError) as excinfo:
        asyncio.run(fetch_inventory(spec, timeout=1.0))
    assert "sleepy" in str(excinfo.value)


def test_fetch_inventory_stdio_without_command():
    spec = ServerSpec(name="broken", transport=Transport.STDIO)
    with pytest.raises(TransportError) as excinfo:
        asyncio.run(fetch_inventory(spec))
    assert "broken" in str(excinfo.value)


def test_fetch_inventory_http_without_url():
    spec = ServerSpec(name="webless", transport=Transport.HTTP)
    with pytest.raises(TransportError) as excinfo:
        asyncio.run(fetch_inventory(spec))
    assert "webless" in str(excinfo.value)
