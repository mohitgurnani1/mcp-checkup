# 🩺 mcp-checkup

**A health check for your MCP setup** — one command that tells you what your
MCP servers cost you in context-window tokens and dollars, and whether they
follow basic security hygiene.

```bash
uvx mcp-checkup
```

## What it does

- **Weigh** — per-tool token cost of every MCP server you run, in
  Anthropic/OpenAI/Gemini wire formats, with $ cost and context-window %
  per model
- **Auto-discovery** — finds servers configured in Claude Desktop,
  Claude Code, Cursor, Windsurf, and VS Code with zero flags
- **Hygiene** — read-only checks for schema bloat, tool-poisoning language,
  unauthenticated remote servers, cross-server shadowing, and rug pulls
- **Fix** — semantic-safe schema compression, upstream issue generation, and
  a trim proxy that enforces the diet permanently
- **CI gate** — `--fail-over` token budgets and severity gates with a stable
  exit-code contract

## Links

- [README](https://github.com/mohitgurnani1/mcp-checkup#readme) — full
  feature tour with real measured output
- [Server gallery](GALLERY.md) — measured context tax of popular servers
- [Roadmap](https://github.com/mohitgurnani1/mcp-checkup/blob/main/ROADMAP.md)
- [Stability contract](https://github.com/mohitgurnani1/mcp-checkup/blob/main/STABILITY.md)
- [PyPI](https://pypi.org/project/mcp-checkup/)
