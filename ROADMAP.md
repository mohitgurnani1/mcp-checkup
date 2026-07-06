# Roadmap

Living document; issues tracked per GitHub milestone:
<https://github.com/mohitgurnani1/mcp-checkup/milestones>

**Status: v0.1.0 → v1.0.0 all shipped.** The CLI, exit codes, and document
schemas are now frozen under the [stability contract](STABILITY.md). Post-1.0
work is tracked as issues (MCP SDK v2 migration, mutation testing).

## v0.1.0 — Weigh one server

- `weigh <target>` — accepts a stdio command, an HTTP(S) URL, or
  `--config <file> --server <name>`
- Per-tool token table across the Anthropic, OpenAI, and Gemini wire formats,
  counted with tiktoken `o200k_base`
- Resources and prompts counted, not just tools
- `--json` output with `schema_version: 1`
- Rich table output for humans

**Done when:** `uvx mcp-checkup weigh "npx -y @modelcontextprotocol/server-filesystem /tmp"`
prints real numbers in under 15 seconds.

## v0.2.0 — Auto-discovery

- Config loaders: Claude Desktop (`claude_desktop_config.json`), Claude Code
  (`.mcp.json` plus `~/.claude.json` scopes), Cursor (`~/.cursor/mcp.json`),
  Windsurf (`~/.codeium/windsurf/mcp_config.json`), VS Code
  (`.vscode/mcp.json`, `servers` key with `inputs` placeholders)
- Zero-flag `mcp-checkup` scans every discovered server concurrently
- Per-server error rows — one broken server never kills the report
- Env values redacted from all output

**Done when:** running bare `mcp-checkup` on a machine with configured clients
reports every server without any flags.

## v0.3.0 — Dollars & context tax

- Vendored LiteLLM pricing snapshot plus an updater script
- $/request and $/session (`--turns`) per server
- Context-tax percentage line per model
- `--model` to select which models the report prices against
- `--precise` — exact Anthropic counts via the `count_tokens` API

**Done when:** the report shows a dollar figure and a context-tax percentage
next to every server, for any model the user names.

## v0.4.0 — Hygiene

- Checks engine: per-check disable flags plus `.mcp-checkup.toml`
- Weight checks: W01 schema-bloat ratio, W02 oversized descriptions,
  W03 enum explosion, W04 tool-count, W05 cross-server duplicates
- Security checks: H01 unauthenticated HTTP, H02 tool-poisoning heuristics
  (invariantlabs taxonomy), H03 cross-server shadowing, H04 dangerous
  capability combos
- Two-pillar WEIGHT | HYGIENE report layout

**Done when:** the default report shows both pillars and every check can be
disabled by flag or config file.

## v0.5.0 — CI gate

- `--fail-over`, `--fail-over-total`, `--fail-on-severity`
- Stable exit codes: 0 ok, 1 budget, 2 hygiene, 3 connect
- `json` and `markdown` output formats with a published report schema
- Baseline write and compare
- Composite GitHub Action, dogfooded in this repo's own CI

**Done when:** a workflow using the action fails a PR that pushes a server
over its token budget, with the documented exit code.

## v0.6.0 — `--fix` emit

- Semantic-safe schema compression — types and `required` never change
- Before/after report showing tokens saved per tool
- `--emit` writes compressed sidecar schema files
- `--emit-pr-text` generates upstream issue text for server authors

**Done when:** `--fix` on a bloated server emits sidecar schemas that
round-trip validation and shows the token delta.

## v0.7.0 — Trim proxy + rug-pull pinning

- `serve --wrap <cmd> --trim` — stdio proxy that re-serves a compressed
  `tools/list`
- `--fix` proxy config rewriter — writes a new config, never edits in place
- H05 changed-since-pin: hashed baselines detect tool definitions that
  changed after you approved them

**Done when:** a client pointed at the trim proxy sees compressed schemas,
and a mutated tool trips H05 against its pinned hash.

## v0.8.0 — Shareable reports

- Self-contained HTML report
- Context-tax badge JSON endpoint
- `diff` command — compare two reports or baselines
- Top-20 popular-server weight gallery in the docs

**Done when:** a single HTML file renders the full report offline and the
badge endpoint serves valid shields.io JSON.

## v0.9.0 — Hardening + SDK v2

- Migrate the transport seam to MCP SDK v2
- Windows CI
- Performance budget: under 5 seconds for 5 servers
- Mutation-testing pass over the checks engine

**Done when:** CI is green on Windows, the perf budget is enforced in CI,
and the mutation score meets the agreed threshold.

## v1.0.0 — Stable

- Freeze CLI surface, exit codes, and `schema_version` with a documented
  deprecation policy
- mkdocs documentation site
- Submissions to MCP directories and awesome lists

**Done when:** 1.0 ships with the compatibility policy published and the docs
site live.
