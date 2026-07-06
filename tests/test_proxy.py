# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the trim proxy: trimmed tools/list, pass-through calls, wrap_config."""

import asyncio
import json
import os
import shlex
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from mcp_checkup.compress import CompressPolicy
from mcp_checkup.models import ToolInfo
from mcp_checkup.proxy import build_proxy_server, wrap_config
from mcp_checkup.serialize import serialize
from mcp_checkup.tokens import count_tokens

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from toy_server import mcp as toy_server

TOY_SERVER_PATH = Path(__file__).parent / "fixtures" / "toy_server.py"


def _tool_tokens(tool) -> int:
    """Anthropic-wire token estimate for an SDK Tool object."""
    info = ToolInfo(
        name=tool.name,
        description=tool.description or "",
        input_schema=tool.inputSchema,
    )
    return count_tokens(serialize(info, "anthropic"))


@asynccontextmanager
async def _memory_proxy(**kwargs):
    """(outer_session, child_session): both hops over in-process memory streams."""
    async with create_connected_server_and_client_session(toy_server) as child:
        caps = child.get_server_capabilities()
        proxy = build_proxy_server(child, caps, **kwargs)
        async with create_connected_server_and_client_session(
            proxy, raise_exceptions=True
        ) as outer:
            yield outer, child


@asynccontextmanager
async def _stdio_child_proxy(**kwargs):
    """(outer_session, child_session): child is a real toy_server subprocess."""
    params = StdioServerParameters(command=sys.executable, args=[str(TOY_SERVER_PATH)])
    with open(os.devnull, "w") as errlog:
        async with (
            stdio_client(params, errlog=errlog) as (read, write),
            ClientSession(read, write) as child,
        ):
            caps = (await child.initialize()).capabilities
            proxy = build_proxy_server(child, caps, **kwargs)
            async with create_connected_server_and_client_session(
                proxy, raise_exceptions=True
            ) as outer:
                yield outer, child


# --- end-to-end round trip ----------------------------------------------------


@pytest.mark.integration
def test_proxy_roundtrip_stdio_child():
    async def run():
        async with _stdio_child_proxy() as (outer, child):
            direct = {t.name: t for t in (await child.list_tools()).tools}

            listed = await outer.list_tools()
            proxied = {t.name: t for t in listed.tools}
            assert set(proxied) == {"add", "greet", "search"} == set(direct)

            # The bloated tool must be strictly lighter through the proxy.
            assert _tool_tokens(proxied["search"]) < _tool_tokens(direct["search"])

            start = time.monotonic()
            result = await outer.call_tool("add", {"a": 2, "b": 3})
            latency = time.monotonic() - start
            assert not result.isError
            assert any(
                isinstance(block, TextContent) and "5" in block.text for block in result.content
            )
            # Generous bound; double hop should be a few ms in practice.
            assert latency < 5.0

    asyncio.run(run())


def test_proxy_trims_all_tools_in_memory():
    async def run():
        async with _memory_proxy() as (outer, child):
            direct = {t.name: t for t in (await child.list_tools()).tools}
            proxied = {t.name: t for t in (await outer.list_tools()).tools}
            for name in direct:
                assert _tool_tokens(proxied[name]) <= _tool_tokens(direct[name])
            # First-sentence policy: rambling description reduced to one sentence.
            assert len(proxied["search"].description) < len(direct["search"].description)
            # Semantic safety: property names survive compression.
            assert set(proxied["search"].inputSchema["properties"]) == set(
                direct["search"].inputSchema["properties"]
            )

    asyncio.run(run())


def test_proxy_trim_false_passes_tools_unchanged():
    async def run():
        async with _memory_proxy(trim=False) as (outer, child):
            direct = {t.name: t for t in (await child.list_tools()).tools}
            proxied = {t.name: t for t in (await outer.list_tools()).tools}
            assert proxied["search"].description == direct["search"].description
            assert proxied["search"].inputSchema == direct["search"].inputSchema

    asyncio.run(run())


def test_proxy_honors_compress_policy():
    async def run():
        policy = CompressPolicy(descriptions="none")
        async with _memory_proxy(policy=policy) as (outer, _child):
            proxied = {t.name: t for t in (await outer.list_tools()).tools}
            assert not proxied["search"].description

    asyncio.run(run())


# --- allow_tools filter ---------------------------------------------------------


def test_allow_tools_filters_listing():
    async def run():
        async with _memory_proxy(allow_tools=["add"]) as (outer, _child):
            listed = await outer.list_tools()
            assert [t.name for t in listed.tools] == ["add"]
            # Allowed tools still work through the proxy.
            result = await outer.call_tool("add", {"a": 40, "b": 2})
            assert not result.isError
            assert any(
                isinstance(block, TextContent) and "42" in block.text for block in result.content
            )

    asyncio.run(run())


# --- resource / prompt pass-throughs --------------------------------------------


def test_resources_and_prompts_pass_through():
    async def run():
        async with _memory_proxy() as (outer, _child):
            resources = (await outer.list_resources()).resources
            assert [str(r.uri) for r in resources] == ["toy://readme"]

            read = await outer.read_resource(resources[0].uri)
            assert "test fixture for mcp-checkup" in read.contents[0].text

            prompts = (await outer.list_prompts()).prompts
            assert [p.name for p in prompts] == ["hello"]

            prompt = await outer.get_prompt("hello", {"name": "proxy"})
            assert "proxy" in prompt.messages[0].content.text

    asyncio.run(run())


def test_missing_child_capabilities_yield_empty_lists():
    async def run():
        async with create_connected_server_and_client_session(toy_server) as child:
            caps = child.get_server_capabilities()
            bare_caps = caps.model_copy(update={"resources": None, "prompts": None})
            proxy = build_proxy_server(child, bare_caps)
            async with create_connected_server_and_client_session(
                proxy, raise_exceptions=True
            ) as outer:
                assert (await outer.list_resources()).resources == []
                assert (await outer.list_prompts()).prompts == []

    asyncio.run(run())


# --- per-call telemetry ----------------------------------------------------------


def test_call_logging_jsonl_and_debug_stderr(tmp_path, monkeypatch, capsys):
    log_path = tmp_path / "proxy.jsonl"
    monkeypatch.setenv("MCP_CHECKUP_PROXY_LOG", str(log_path))
    monkeypatch.setenv("MCP_CHECKUP_DEBUG", "1")

    async def run():
        async with _memory_proxy() as (outer, _child):
            await outer.call_tool("add", {"a": 1, "b": 2})
            await outer.call_tool("greet", {"name": "bob"})

    asyncio.run(run())

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [r["tool"] for r in records] == ["add", "greet"]
    for record in records:
        assert set(record) == {"tool", "ts_monotonic_delta", "ok"}
        assert record["ok"] is True
        assert isinstance(record["ts_monotonic_delta"], float)
        assert record["ts_monotonic_delta"] >= 0.0
    # Monotonic deltas from a shared epoch never go backwards.
    assert records[0]["ts_monotonic_delta"] <= records[1]["ts_monotonic_delta"]

    stderr = capsys.readouterr().err
    assert stderr.count("[mcp-checkup-proxy]") == 2
    assert "tool=add ok=True" in stderr


def test_no_logging_without_env(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MCP_CHECKUP_PROXY_LOG", raising=False)
    monkeypatch.delenv("MCP_CHECKUP_DEBUG", raising=False)

    async def run():
        async with _memory_proxy() as (outer, _child):
            await outer.call_tool("add", {"a": 1, "b": 2})

    asyncio.run(run())
    assert "[mcp-checkup-proxy]" not in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


# --- wrap_config -----------------------------------------------------------------


def test_wrap_config_wraps_stdio_with_shell_quoting():
    config = {
        "mcpServers": {
            "fs": {
                "command": "npx",
                "args": ["-y", "server-filesystem", "/tmp/my docs"],
                "env": {"FS_ROOT": "/tmp"},
            }
        }
    }
    wrapped = wrap_config(config)["mcpServers"]["fs"]
    assert wrapped["command"] == "mcp-checkup"
    assert wrapped["args"] == [
        "serve",
        "--wrap",
        "npx -y server-filesystem '/tmp/my docs'",
        "--trim",
    ]
    assert wrapped["env"] == {"FS_ROOT": "/tmp"}
    # Round-trip: the quoted string splits back into the original command line.
    assert shlex.split(wrapped["args"][2]) == ["npx", "-y", "server-filesystem", "/tmp/my docs"]


def test_wrap_config_appends_policy_args():
    config = {"mcpServers": {"toy": {"command": "toy-server"}}}
    wrapped = wrap_config(config, policy_args=["--descriptions", "none"])
    assert wrapped["mcpServers"]["toy"]["args"] == [
        "serve",
        "--wrap",
        "toy-server",
        "--trim",
        "--descriptions",
        "none",
    ]


def test_wrap_config_leaves_http_entries_unchanged():
    config = {
        "mcpServers": {
            "web": {"url": "https://example.com/mcp", "headers": {"x-key": "k"}},
            "local": {"command": "local-server"},
        }
    }
    wrapped = wrap_config(config)["mcpServers"]
    assert wrapped["web"] == {"url": "https://example.com/mcp", "headers": {"x-key": "k"}}
    assert wrapped["local"]["command"] == "mcp-checkup"


def test_wrap_config_is_a_deep_copy():
    env = {"TOKEN": "secret"}
    config = {"mcpServers": {"toy": {"command": "toy-server", "args": ["--x"], "env": env}}}
    wrapped = wrap_config(config)

    # Input untouched, even in nested structures.
    assert config["mcpServers"]["toy"]["command"] == "toy-server"
    assert config["mcpServers"]["toy"]["env"] is env

    # Output shares no mutable state with the input.
    wrapped["mcpServers"]["toy"]["env"]["TOKEN"] = "changed"
    assert env["TOKEN"] == "secret"


def test_wrap_config_preserves_servers_key():
    config = {"servers": {"toy": {"command": "toy-server"}}}
    wrapped = wrap_config(config)
    assert set(wrapped) == {"servers"}
    assert wrapped["servers"]["toy"]["command"] == "mcp-checkup"


def test_wrap_config_omits_env_when_absent():
    config = {"mcpServers": {"toy": {"command": "toy-server"}}}
    wrapped = wrap_config(config)
    assert "env" not in wrapped["mcpServers"]["toy"]
