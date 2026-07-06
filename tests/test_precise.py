# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from mcp_checkup.models import ToolInfo
from mcp_checkup.precise import count_precise

TOOLS = [
    ToolInfo(
        name="get_weather",
        description="Get current weather for a city.",
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
]


def test_no_api_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert count_precise(TOOLS, "claude-sonnet-5") is None


def test_import_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "anthropic", None)  # forces ImportError
    assert count_precise(TOOLS, "claude-sonnet-5") is None


def test_fake_anthropic_module_returns_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: list[dict[str, Any]] = []

    @dataclass
    class FakeCount:
        input_tokens: int

    class FakeMessages:
        def count_tokens(self, **kwargs: Any) -> FakeCount:
            calls.append(kwargs)
            return FakeCount(input_tokens=123)

    class FakeAnthropic:
        def __init__(self) -> None:
            self.messages = FakeMessages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    assert count_precise(TOOLS, "claude-sonnet-5") == 123

    (kwargs,) = calls
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert kwargs["tools"] == [
        {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "input_schema": TOOLS[0].input_schema,
        }
    ]
