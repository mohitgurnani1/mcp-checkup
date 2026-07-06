# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Auto-discovery of MCP server configs from installed clients."""

from mcp_checkup.discovery.base import CLIENTS, Discovered, discover_all

__all__ = ["CLIENTS", "Discovered", "discover_all"]
