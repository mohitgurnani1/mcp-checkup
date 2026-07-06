# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

import json
import urllib.request
from importlib import resources

import pytest

from mcp_checkup.pricing import (
    DEFAULT_MODELS,
    ModelPrice,
    cost_line,
    load_pricing,
    resolve_models,
)

VALID_PROVIDERS = {"anthropic", "openai", "gemini"}


def test_vendored_snapshot_exists_and_is_sane() -> None:
    raw = resources.files("mcp_checkup.data").joinpath("pricing.json").read_text("utf-8")
    snapshot = json.loads(raw)
    assert snapshot["generated_from"] == "litellm"
    assert snapshot["models"]
    for key, entry in snapshot["models"].items():
        assert entry["input_cost_per_token"] > 0, key
        assert entry["max_input_tokens"] > 0, key
        assert entry["provider"] in VALID_PROVIDERS, key
        assert entry["display"], key


def test_load_pricing_returns_model_prices() -> None:
    pricing = load_pricing()
    assert pricing
    for key, model in pricing.items():
        assert isinstance(model, ModelPrice)
        assert model.key == key
        assert model.input_cost_per_token > 0
        assert model.max_input_tokens > 0
        assert model.provider in VALID_PROVIDERS


def test_default_models_all_resolve() -> None:
    pricing = load_pricing()
    resolved = resolve_models(None, pricing)
    assert [m.key for m in resolved] == DEFAULT_MODELS
    assert {m.provider for m in resolved} == VALID_PROVIDERS  # one per provider


def test_cost_line_golden() -> None:
    model = ModelPrice(
        key="test-model",
        display="Test Model",
        provider="anthropic",
        input_cost_per_token=3e-06,
        max_input_tokens=200_000,
    )
    info = cost_line(model, tokens=10_000)
    assert info.usd_per_request == pytest.approx(0.03)
    assert info.usd_per_session == pytest.approx(0.03)  # turns defaults to 1
    assert info.context_pct == pytest.approx(5.0)
    info10 = cost_line(model, tokens=10_000, turns=10)
    assert info10.usd_per_request == pytest.approx(0.03)
    assert info10.usd_per_session == pytest.approx(0.30)


def test_resolve_models_explicit_names() -> None:
    pricing = load_pricing()
    key = DEFAULT_MODELS[0]
    resolved = resolve_models([key], pricing)
    assert len(resolved) == 1
    assert resolved[0] is pricing[key]


def test_resolve_models_unknown_raises_with_available_keys() -> None:
    pricing = load_pricing()
    with pytest.raises(ValueError, match="no-such-model") as excinfo:
        resolve_models(["no-such-model"], pricing)
    for key in pricing:
        assert key in str(excinfo.value)


def test_load_pricing_refresh_falls_back_on_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert load_pricing(refresh=True) == load_pricing(refresh=False)


def test_load_pricing_refresh_overlays_live_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    key = DEFAULT_MODELS[0]

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            live = {key: {"input_cost_per_token": 9e-06, "max_input_tokens": 123_456}}
            return json.dumps(live).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse())
    pricing = load_pricing(refresh=True)
    assert pricing[key].input_cost_per_token == pytest.approx(9e-06)
    assert pricing[key].max_input_tokens == 123_456
    # Models absent from the live table keep their vendored values.
    other = next(k for k in pricing if k != key)
    assert pricing[other] == load_pricing()[other]
