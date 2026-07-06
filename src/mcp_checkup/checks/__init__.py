# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Hygiene checks: weight (W..) and security (H..) rules over server inventories."""

from mcp_checkup.checks.base import CHECKS, Finding, Severity, run_checks

__all__ = ["CHECKS", "Finding", "Severity", "run_checks"]
