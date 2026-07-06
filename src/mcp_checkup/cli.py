# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry point for mcp-checkup."""

import argparse
import asyncio
import json
import sys

from mcp_checkup import __version__
from mcp_checkup.models import ServerSpec, Transport


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-checkup",
        description="🩺 Measure the context tax and hygiene of your MCP servers.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    weigh = sub.add_parser(
        "weigh",
        help="Weigh one MCP server: per-tool token cost of its schemas",
        description=(
            "Connect to a single MCP server and report the token cost of every "
            "tool schema in Anthropic/OpenAI/Gemini wire formats."
        ),
    )
    weigh.add_argument(
        "target",
        nargs="?",
        help='Server to weigh: a stdio command (e.g. "npx -y @modelcontextprotocol/'
        'server-filesystem /tmp") or an http(s) URL',
    )
    weigh.add_argument("--config", help="Path to an mcpServers-style JSON config file")
    weigh.add_argument("--server", help="Server name inside --config to weigh")
    weigh.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    weigh.add_argument(
        "--timeout", type=float, default=10.0, help="Connection timeout in seconds (default 10)"
    )
    return parser


def _spec_from_config(path: str, server: str | None) -> ServerSpec:
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    servers = config.get("mcpServers") or config.get("servers") or {}
    if not servers:
        raise SystemExit(f"error: no mcpServers found in {path}")
    if server is None:
        if len(servers) > 1:
            names = ", ".join(sorted(servers))
            raise SystemExit(f"error: multiple servers in {path}; pick one with --server ({names})")
        server = next(iter(servers))
    if server not in servers:
        raise SystemExit(f"error: server {server!r} not in {path}")
    entry = servers[server]
    if entry.get("url"):
        return ServerSpec(
            name=server,
            transport=Transport.HTTP,
            url=entry["url"],
            headers=entry.get("headers", {}),
        )
    return ServerSpec(
        name=server,
        transport=Transport.STDIO,
        command=entry["command"],
        args=entry.get("args", []),
        env=entry.get("env", {}),
    )


def _cmd_weigh(args: argparse.Namespace) -> int:
    from mcp_checkup.render import print_table, to_json
    from mcp_checkup.tokens import weigh_inventory
    from mcp_checkup.transport import TransportError, fetch_inventory, parse_target

    if args.config:
        spec = _spec_from_config(args.config, args.server)
    elif args.target:
        spec = parse_target(args.target)
    else:
        raise SystemExit("error: provide a target command/URL or --config")

    try:
        inventory = asyncio.run(fetch_inventory(spec, timeout=args.timeout))
    except TransportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    result = weigh_inventory(inventory)
    if args.as_json:
        print(to_json(result))
    else:
        print_table(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "weigh":
        return _cmd_weigh(args)
    parser.print_help()
    return 0
