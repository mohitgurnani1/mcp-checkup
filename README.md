# 🩺 mcp-checkup

**A health check for your MCP setup.**

One command that tells you what your MCP servers *cost* you — in context-window
tokens and dollars — and whether they follow basic security hygiene.

[![CI][badge-ci]][ci] [![PyPI][badge-pypi]][pypi] [![Python][badge-py]][pypi]
[![License][badge-license]][license] [![Ruff][badge-ruff]][ruff]

---

## The problem

Every MCP server you connect injects its full tool schemas into your model's
context window — on **every single request** — before you type a word.

- GitHub's official MCP server alone consumes **~17,600 tokens per request** in
  tool definitions ([autopsy][gh-mcp-cost]).
- Teams have burned **72% of a 200k context window** on tool definitions before
  doing any actual work ([MCP spec issue #2808][spec-2808]).
- A security audit of publicly exposed MCP servers found **119 out of 119
  sampled allowed unauthenticated access** to internal tool listings.

You are paying a *context tax* on every request, and you probably have no idea
how big it is. `mcp-checkup` measures it.

## What it looks like

Real output of a bare `uvx mcp-checkup` on a developer laptop (v0.2.0):

```text
$ uvx mcp-checkup

  🩺 MCP Checkup — 5 server(s), 128 tools
  ┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
  ┃ Server        ┃ Clients        ┃ Tools ┃ anthropic ┃ openai ┃ gemini ┃
  ┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
  │ alpaca        │ claude-code    │    69 │    18,611 │ 19,025 │ 18,542 │
  │ edgartools    │ claude-code    │    13 │     3,725 │  3,803 │  3,712 │
  │ playwright    │ claude-desktop │    23 │     3,198 │  3,336 │  3,175 │
  │ filesystem    │ claude-desktop │    14 │     1,640 │  1,723 │  1,626 │
  │ yahoo-finance │ claude-code    │     9 │     1,396 │  1,450 │  1,387 │
  ├───────────────┼────────────────┼───────┼───────────┼────────┼────────┤
  │ Total         │                │   128 │    28,570 │ 29,337 │ 28,442 │
  └───────────────┴────────────────┴───────┴───────────┴────────┴────────┘
  Context tax: ~28,916 tokens on Anthropic models (incl. 346 tool-use
  system overhead), before your first message.
```

That's 14% of a 200k context window, spent before the first user message.

### Supported clients (auto-discovery)

| Client | Config discovered |
| --- | --- |
| Claude Desktop | `claude_desktop_config.json` (macOS/Windows/Linux) |
| Claude Code | project `.mcp.json` + `~/.claude.json` user/local scopes |
| Cursor | `~/.cursor/mcp.json` + project `.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| VS Code | `.vscode/mcp.json` + user-profile `mcp.json` (`servers` key) |

### Hygiene checks

Every scan also runs read-only hygiene checks over what your servers
advertise — sample real findings:

```text
  Hygiene findings (10)
  W01 medium alpaca > get_portfolio_history: tool is 8.7x its minimal schema (1443 vs 166 tokens)
  W01 medium alpaca > replace_order_by_id:   tool is 3.3x its minimal schema (1501 vs 451 tokens)
  W04 low    alpaca: server exposes 69 tools; models degrade with large tool lists
  W05 low    get_option_chain is advertised by 2 servers: alpaca, yahoo-finance
```

| ID | Checks for |
| --- | --- |
| W01–W05 | Schema bloat vs minimal equivalent, oversized descriptions, enum explosions, tool-count explosion, cross-server duplicate tools |
| H01 | Remote HTTP servers configured without client credentials |
| H02 | Tool-poisoning language in descriptions (hidden instructions, concealment, sensitive-path exfiltration) |
| H03 | Cross-server tool shadowing ("instead of X, always…") |
| H04 | Write/exec tools alongside network-fetch tools (exfiltration-chain heuristic) |

All checks are heuristics — disable any with `--disable-check ID`; see details
with `--verbose`. For deep security-only scanning also consider
[invariantlabs' mcp-scan][mcp-scan]; mcp-checkup's focus is the combined
cost + hygiene physical.

## Quickstart

```bash
uvx mcp-checkup          # or: pip install mcp-checkup
```

Point it at your client config (`.mcp.json`, Claude Desktop, Cursor, …) or a
running server. That's the whole interface — one command, one report.

## Roadmap

Full detail per milestone in [ROADMAP.md](ROADMAP.md).

| Version | Theme                       | One line                                                            |
| ------- | --------------------------- | ------------------------------------------------------------------- |
| v0.1.0  | Weigh one server            | `weigh <target>` prints a per-tool token table for one server        |
| v0.2.0  | Auto-discovery              | Zero-flag scan of Claude Desktop/Code, Cursor, Windsurf, VS Code     |
| v0.3.0  | Dollars & context tax       | $/request, $/session, and context-tax % per model                    |
| v0.4.0  | Hygiene                     | Weight (W01–W05) and security (H01–H04) checks, two-pillar report    |
| v0.5.0  | CI gate                     | Budget/severity gates, stable exit codes, GitHub Action              |
| v0.6.0  | `--fix` emit                | Semantic-safe schema compression with before/after report            |
| v0.7.0  | Trim proxy + rug-pull pins  | `serve --wrap --trim` proxy, changed-since-pin detection             |
| v0.8.0  | Shareable reports           | Self-contained HTML report, badge endpoint, `diff` command           |
| v0.9.0  | Hardening + SDK v2          | MCP SDK v2 transport, Windows CI, perf budget                        |
| v1.0.0  | Stable                      | Frozen CLI/exit codes/schema with a deprecation policy               |

## How counting works (and its error bars)

Each tool schema is serialized into every provider's actual wire format
(Anthropic `tools`, OpenAI `functions`, Gemini `functionDeclarations`) and
counted with tiktoken's `o200k_base` encoding — exact for the GPT-4o/GPT-5
family, a close proxy (±~10%) for Anthropic and Gemini. Anthropic totals add
the documented tool-use system-prompt overhead. For billing-exact Anthropic
numbers, install `mcp-checkup[precise]`, set `ANTHROPIC_API_KEY`, and pass
`--precise` — it queries the free `count_tokens` API with your real schemas.

Prices and context windows come from a vendored snapshot of LiteLLM's
community-maintained pricing table; `--refresh-pricing` fetches the latest at
runtime (with silent fallback). `$ per session` assumes schemas are resent
every turn — with prompt caching you pay full price on turn one and on every
cache invalidation.

## Status

Early days — the measurement engine is being built in the open. If the context
tax bothers you too: ⭐ star the repo to follow along, open an issue with your
worst MCP token bill, or see [CONTRIBUTING.md](CONTRIBUTING.md) to help build it.

## License

[Apache-2.0](LICENSE)

[badge-ci]: https://github.com/mohitgurnani1/mcp-checkup/actions/workflows/ci.yaml/badge.svg
[ci]: https://github.com/mohitgurnani1/mcp-checkup/actions/workflows/ci.yaml
[badge-pypi]: https://img.shields.io/pypi/v/mcp-checkup
[pypi]: https://pypi.org/project/mcp-checkup/
[badge-py]: https://img.shields.io/pypi/pyversions/mcp-checkup
[badge-license]: https://img.shields.io/badge/license-Apache--2.0-blue
[license]: LICENSE
[badge-ruff]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[ruff]: https://github.com/astral-sh/ruff
[gh-mcp-cost]: https://getunblocked.com/blog/github-mcp-token-cost/
[spec-2808]: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2808
[mcp-scan]: https://github.com/invariantlabs-ai/mcp-scan
