# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry point for mcp-checkup."""

import argparse

from mcp_checkup import __version__

BANNER = r"""
                                 _               _
  _ __ ___   ___ _ __        ___| |__   ___  ___| | ___   _ _ __
 | '_ ` _ \ / __| '_ \ _____/ __| '_ \ / _ \/ __| |/ / | | | '_ \
 | | | | | | (__| |_) |____| (__| | | |  __/ (__|   <| |_| | |_) |
 |_| |_| |_|\___| .__/      \___|_| |_|\___|\___|_|\_\\__,_| .__/
                |_|                                        |_|
"""

ROADMAP = """\
🩺 mcp-checkup — a health check for your MCP setup

This is an early preview. The full checkup is under active development:

  [ ] WEIGHT   per-tool token cost of every MCP server you run
  [ ] WEIGHT   $ cost per session, per model
  [ ] HYGIENE  missing auth, exposed tool listings
  [ ] HYGIENE  bloated / injection-prone schemas
  [ ] --fix    emit compressed schemas
  [ ] CI mode  --fail-over <token-budget>

Follow along: https://github.com/mohitgurnani1/mcp-checkup
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-checkup",
        description="Measure the context tax and hygiene of your MCP servers.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)

    print(BANNER)
    print(ROADMAP)
    return 0
