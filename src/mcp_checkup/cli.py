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
    _add_cost_flags(weigh)
    weigh.add_argument(
        "--precise",
        action="store_true",
        help="Also query Anthropic's count_tokens API for an exact count "
        "(needs ANTHROPIC_API_KEY and the [precise] extra)",
    )

    scan = sub.add_parser(
        "scan",
        help="Discover MCP servers from installed clients and weigh them all (default)",
        description=(
            "Find MCP server configs from Claude Desktop, Claude Code, Cursor, "
            "Windsurf, and VS Code, then weigh every server concurrently."
        ),
    )
    scan.add_argument(
        "--client",
        action="append",
        dest="clients",
        choices=["claude-desktop", "claude-code", "cursor", "windsurf", "vscode"],
        help="Only scan configs of this client (repeatable)",
    )
    scan.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    scan.add_argument(
        "--format",
        choices=["table", "json", "markdown"],
        default=None,
        help="Output format (default table; --json is shorthand for --format json)",
    )
    scan.add_argument(
        "--timeout", type=float, default=10.0, help="Per-server connection timeout (default 10)"
    )
    scan.add_argument(
        "--fail-over",
        type=int,
        metavar="TOKENS",
        help="Exit 1 if any single server's tool definitions exceed this many "
        "tokens (anthropic estimate)",
    )
    scan.add_argument(
        "--fail-over-total",
        type=int,
        metavar="TOKENS",
        help="Exit 1 if the combined tool definitions exceed this many tokens",
    )
    scan.add_argument(
        "--fail-on-severity",
        choices=["low", "medium", "high"],
        help="Exit 2 if any hygiene finding at or above this severity exists",
    )
    scan.add_argument(
        "--quiet",
        action="store_true",
        help="No report output; only gate messages and the exit code",
    )
    scan.add_argument(
        "--write-baseline",
        nargs="?",
        const=".mcp-checkup-baseline.json",
        metavar="PATH",
        help="Write a baseline snapshot (default .mcp-checkup-baseline.json)",
    )
    scan.add_argument(
        "--baseline",
        default=".mcp-checkup-baseline.json",
        metavar="PATH",
        help="Baseline file to compare against when it exists",
    )
    _add_cost_flags(scan)

    fix = sub.add_parser(
        "fix",
        help="Compress a server's tool schemas and show the token savings",
        description=(
            "Build semantic-safe compressed versions of a server's tool "
            "schemas (types/required/names never change) and report the "
            "before/after token cost. Optionally emit sidecar schema files "
            "or a ready-to-file upstream issue."
        ),
    )
    fix.add_argument("target", nargs="?", help="Server: stdio command or http(s) URL")
    fix.add_argument("--config", help="Path to an mcpServers-style JSON config file")
    fix.add_argument("--server", help="Server name inside --config")
    fix.add_argument(
        "--timeout", type=float, default=10.0, help="Connection timeout in seconds (default 10)"
    )
    fix.add_argument(
        "--keep-descriptions",
        choices=["none", "first-sentence", "full"],
        default="first-sentence",
        help="How much description text the compressed schemas keep (default first-sentence)",
    )
    fix.add_argument(
        "--emit",
        metavar="DIR",
        help="Write compressed sidecar schema files + TOOLS.md into DIR",
    )
    fix.add_argument(
        "--emit-pr-text",
        metavar="FILE",
        help="Write a ready-to-paste upstream issue body to FILE",
    )
    fix.add_argument(
        "--emit-proxy-config",
        metavar="FILE",
        help="With --config: write a copy of the client config where every "
        "stdio server is wrapped in the trim proxy (never edits in place)",
    )

    serve = sub.add_parser(
        "serve",
        help="Run the trim proxy: a stdio MCP server wrapping another server",
        description=(
            "Sits between your client and an MCP server: re-serves a "
            "compressed tools/list while passing tool calls through "
            "unchanged. Point your client at this command instead of the "
            "original server."
        ),
    )
    serve.add_argument(
        "--wrap",
        required=True,
        metavar="COMMAND",
        help="The wrapped server's stdio command, quoted as one string",
    )
    serve.add_argument(
        "--trim",
        action="store_true",
        default=True,
        help="Serve compressed tool schemas (default on)",
    )
    serve.add_argument(
        "--no-trim", action="store_false", dest="trim", help="Pass schemas through unchanged"
    )
    serve.add_argument(
        "--allow-tools",
        metavar="NAMES",
        help="Comma-separated allowlist; other tools are hidden from the client",
    )
    serve.add_argument(
        "--keep-descriptions",
        choices=["none", "first-sentence", "full"],
        default="first-sentence",
        help="Description policy for trimmed schemas",
    )
    return parser


def _add_cost_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--model",
        action="append",
        dest="model_names",
        metavar="MODEL",
        help="Model to price against (repeatable; default: one flagship per provider)",
    )
    p.add_argument(
        "--turns",
        type=int,
        default=10,
        help="Conversation turns for $/session estimate (default 10)",
    )
    p.add_argument(
        "--refresh-pricing",
        action="store_true",
        help="Fetch latest prices from LiteLLM's table (falls back to vendored snapshot)",
    )
    p.add_argument("--no-cost", action="store_true", help="Skip the cost section")
    p.add_argument(
        "--disable-check",
        action="append",
        dest="disabled_checks",
        metavar="ID",
        help="Disable a hygiene check by id, e.g. W01 (repeatable)",
    )
    p.add_argument("--verbose", action="store_true", help="Show hygiene finding details")


def _resolve_cost_models(args: argparse.Namespace):
    from mcp_checkup.pricing import load_pricing, resolve_models

    pricing = load_pricing(refresh=args.refresh_pricing)
    try:
        return resolve_models(args.model_names, pricing)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc


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
    models = None if args.no_cost else _resolve_cost_models(args)

    from mcp_checkup.checks import run_checks

    findings = run_checks([inventory], disabled=set(args.disabled_checks or []))

    precise_count = None
    if args.precise:
        from mcp_checkup.precise import count_precise

        anthropic_model = next((m.key for m in models or [] if m.provider == "anthropic"), None)
        precise_count = count_precise(inventory.tools, anthropic_model or "claude-sonnet-4-5")
        if precise_count is None:
            print(
                "note: --precise skipped (install mcp-checkup[precise] and set ANTHROPIC_API_KEY)",
                file=sys.stderr,
            )

    if args.as_json:
        import json as _json

        doc = _json.loads(to_json(result))
        if models:
            from mcp_checkup.render import costs_doc

            doc["costs"] = costs_doc(result.totals(), models, args.turns)
        if precise_count is not None:
            doc["precise_anthropic_tokens"] = precise_count
        from mcp_checkup.render import findings_doc

        doc["findings"] = findings_doc(findings)
        print(_json.dumps(doc, indent=2))
    else:
        print_table(result)
        if models:
            from mcp_checkup.render import print_cost_section

            print_cost_section(result.totals(), models, args.turns)
        if precise_count is not None:
            print(f"Precise Anthropic count (count_tokens API): {precise_count:,} tokens")
        from mcp_checkup.render import print_findings

        print_findings(findings, verbose=args.verbose)
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    from mcp_checkup.render import print_scan_table, scan_to_json
    from mcp_checkup.scan import run_scan

    report = asyncio.run(
        run_scan(
            clients=args.clients,
            timeout=args.timeout,
            disabled_checks=set(args.disabled_checks or []),
        )
    )
    if not report.entries:
        print(
            "No MCP servers found in Claude Desktop/Code, Cursor, Windsurf, or "
            "VS Code configs.\nWeigh one directly: mcp-checkup weigh '<command or url>'",
            file=sys.stderr,
        )
        return 0
    models = None if args.no_cost else _resolve_cost_models(args)
    fmt = args.format or ("json" if args.as_json else "table")

    cost_entries = None
    if models:
        from mcp_checkup.render import costs_doc

        cost_entries = costs_doc(report.totals(), models, args.turns)

    if args.quiet:
        pass
    elif fmt == "json":
        import json as _json

        doc = _json.loads(scan_to_json(report))
        if cost_entries:
            doc["costs"] = cost_entries
        print(_json.dumps(doc, indent=2))
    elif fmt == "markdown":
        from mcp_checkup.markdown import scan_to_markdown

        print(scan_to_markdown(report, costs=cost_entries))
    else:
        print_scan_table(report)
        if models and any(e.result for e in report.entries):
            from mcp_checkup.render import print_cost_section

            print_cost_section(report.totals(), models, args.turns)
        from mcp_checkup.render import print_findings

        print_findings(report.findings, verbose=args.verbose)

    from mcp_checkup import baseline as baseline_mod

    if args.write_baseline:
        baseline_mod.write(report, args.write_baseline)
        print(f"baseline written to {args.write_baseline}", file=sys.stderr)
    elif args.baseline:
        base = baseline_mod.load(args.baseline)
        if base:
            for line in baseline_mod.compare(report, base):
                print(f"baseline: {line}", file=sys.stderr)
            if "H05" not in set(args.disabled_checks or []):
                from mcp_checkup.checks.base import Finding, Severity

                for server, tool in baseline_mod.hash_changes(report, base):
                    report.findings.insert(
                        0,
                        Finding(
                            check_id="H05",
                            severity=Severity.HIGH,
                            server=server,
                            tool=tool,
                            summary="tool definition changed since it was pinned "
                            "in the baseline (possible rug pull)",
                            detail="Re-review the tool, then refresh the pin with "
                            "--write-baseline.",
                        ),
                    )
                    print(
                        f"H05: tool {tool!r} on {server!r} changed since baseline pin",
                        file=sys.stderr,
                    )

    return _scan_exit_code(args, report)


_SEV_RANK = {"low": 0, "medium": 1, "high": 2}


def _scan_exit_code(args: argparse.Namespace, report) -> int:
    if report.entries and all(e.error for e in report.entries):
        return 3
    if args.fail_over is not None:
        for e in report.entries:
            if e.result and e.result.totals().get("anthropic", 0) > args.fail_over:
                print(
                    f"budget exceeded: server {e.discovered.spec.name!r} is "
                    f"{e.result.totals()['anthropic']:,} tokens (limit {args.fail_over:,})",
                    file=sys.stderr,
                )
                return 1
    if args.fail_over_total is not None:
        total = report.totals().get("anthropic", 0)
        if total > args.fail_over_total:
            print(
                f"budget exceeded: total {total:,} tokens (limit {args.fail_over_total:,})",
                file=sys.stderr,
            )
            return 1
    if args.fail_on_severity:
        threshold = _SEV_RANK[args.fail_on_severity]
        bad = [f for f in report.findings if _SEV_RANK[f.severity.value] >= threshold]
        if bad:
            print(
                f"hygiene gate: {len(bad)} finding(s) at or above severity {args.fail_on_severity}",
                file=sys.stderr,
            )
            return 2
    return 0


def _cmd_fix(args: argparse.Namespace) -> int:
    from pathlib import Path

    from rich.console import Console

    from mcp_checkup.compress import CompressPolicy
    from mcp_checkup.fixer import build_report, emit_sidecars, pr_text, render_fix_table
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

    policy = CompressPolicy(descriptions=args.keep_descriptions)
    report = build_report(inventory, policy)
    render_fix_table(report, Console())

    if args.emit:
        paths = emit_sidecars(inventory, policy, Path(args.emit))
        print(f"wrote {len(paths)} file(s) to {args.emit}", file=sys.stderr)
    if args.emit_pr_text:
        Path(args.emit_pr_text).write_text(pr_text(inventory, report), encoding="utf-8")
        print(f"wrote upstream issue text to {args.emit_pr_text}", file=sys.stderr)
    if args.emit_proxy_config:
        if not args.config:
            raise SystemExit("error: --emit-proxy-config requires --config")
        from mcp_checkup.proxy import wrap_config

        with open(args.config, encoding="utf-8") as f:
            original = json.load(f)
        out = Path(args.emit_proxy_config)
        out.write_text(json.dumps(wrap_config(original), indent=2) + "\n", encoding="utf-8")
        print(
            f"wrote proxied config to {out} — review it, then swap it in for "
            f"{args.config} in your client settings",
            file=sys.stderr,
        )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from mcp_checkup.compress import CompressPolicy
    from mcp_checkup.proxy import run_proxy

    allow = [t.strip() for t in args.allow_tools.split(",")] if args.allow_tools else None
    policy = CompressPolicy(descriptions=args.keep_descriptions)
    asyncio.run(run_proxy(args.wrap, trim=args.trim, allow_tools=allow, policy=policy))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "weigh":
        return _cmd_weigh(args)
    if args.command == "scan":
        return _cmd_scan(args)
    if args.command == "fix":
        return _cmd_fix(args)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command is None and (argv is None or not argv):
        # Bare `mcp-checkup` = scan with defaults.
        return main(["scan"])
    parser.print_help()
    return 0
