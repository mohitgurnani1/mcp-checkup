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

> ⚠️ **Target UX.** The WEIGHT column ships in v0.1.0; the HYGIENE column
> arrives in v0.4.0. Until then the output below is the design we are building
> toward.

```text
$ uvx mcp-checkup

  🩺 MCP Checkup — 4 servers, 38 tools

  WEIGHT                                    HYGIENE
  ────────────────────────────────────     ─────────────────────────────────
  github       17,612 tok   $0.053/req     ⚠ 2 tools reachable without auth
  slack         4,105 tok   $0.012/req     ✓ ok
  filesystem    2,890 tok   $0.009/req     ⚠ unrestricted root path
  custom-api    9,441 tok   $0.028/req     ⚠ 3 schemas 8× over minimal size

  Context tax: 34,048 tokens — 17% of a 200k window, before your first message.

  Run `mcp-checkup --fix` to emit compressed schemas.
  Run `mcp-checkup --fail-over 20000` in CI to stop the bloat from coming back.
```

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
