# Context-tax gallery

Measured tool-definition weight (Anthropic wire format, tiktoken
`o200k_base`) of popular MCP servers. Regenerate with
`uv run python scripts/weigh_gallery.py`.

_Last measured: 2026-07-06._

| Server | Tools | Tokens/request |
| --- | ---: | ---: |
| github | 26 | 3,546 |
| playwright | 23 | 3,198 |
| filesystem | 14 | 1,640 |
| git | 12 | 1,117 |
| everything (reference) | 13 | 1,084 |
| memory | 9 | 900 |
| sequential-thinking | 1 | 852 |
| puppeteer | 8 | 502 |
| time | 2 | 237 |
| fetch | 1 | 236 |

Not measurable in this run:

- brave-search: unhandled errors in a TaskGroup (1 sub-exception)
