# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Regenerate the vendored pricing snapshot from LiteLLM's price table.

Fetches https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json,
filters it down to a curated allowlist of flagship/workhorse models, and
writes ``src/mcp_checkup/data/pricing.json``. Stdlib only — run directly:

    python scripts/update_pricing.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "mcp_checkup" / "data" / "pricing.json"

# Curated allowlist: litellm key -> human-readable display name. Keys must
# exist in the fetched table and carry both input_cost_per_token and
# max_input_tokens, or they are skipped with a warning.
ALLOWLIST: dict[str, str] = {
    # Anthropic
    "claude-fable-5": "Claude Fable 5",
    "claude-opus-4-8": "Claude Opus 4.8",
    "claude-sonnet-5": "Claude Sonnet 5",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-haiku-4-5": "Claude Haiku 4.5",
    # OpenAI
    "gpt-5.5": "GPT-5.5",
    "gpt-5.4": "GPT-5.4",
    "gpt-5.4-mini": "GPT-5.4 Mini",
    "gpt-5.1": "GPT-5.1",
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o Mini",
    # Gemini
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro (preview)",
    "gemini-3-flash-preview": "Gemini 3 Flash (preview)",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
}


def provider_bucket(key: str, entry: dict) -> str | None:
    """Map a litellm entry to one of mcp-checkup's provider buckets."""
    litellm_provider = str(entry.get("litellm_provider", ""))
    if litellm_provider == "anthropic" or key.startswith("claude"):
        return "anthropic"
    if litellm_provider == "openai" or key.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if (
        litellm_provider in ("gemini", "vertex_ai-language-models")
        or litellm_provider.startswith("vertex_ai")
        or key.startswith("gemini")
    ):
        return "gemini"
    return None


def main() -> int:
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as resp:
        table = json.load(resp)

    models: dict[str, dict] = {}
    for key, display in ALLOWLIST.items():
        entry = table.get(key)
        if not isinstance(entry, dict):
            print(f"skip {key}: not found upstream", file=sys.stderr)
            continue
        cost = entry.get("input_cost_per_token")
        max_input = entry.get("max_input_tokens")
        if not isinstance(cost, (int, float)) or not isinstance(max_input, int):
            print(f"skip {key}: missing input_cost_per_token or max_input_tokens", file=sys.stderr)
            continue
        provider = provider_bucket(key, entry)
        if provider is None:
            print(f"skip {key}: cannot infer provider bucket", file=sys.stderr)
            continue
        models[key] = {
            "input_cost_per_token": float(cost),
            "max_input_tokens": max_input,
            "display": display,
            "provider": provider,
        }

    if not models:
        print("no models matched the allowlist; refusing to write empty snapshot", file=sys.stderr)
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"generated_from": "litellm", "models": models}, indent=2, sort_keys=True) + "\n"
    )
    print(f"wrote {len(models)} models to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
