# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Schema compression: shrink tool definitions without changing what they accept.

This module extends the approach of :func:`mcp_checkup.checks.weight.minimal_schema`
(strip documentation keys, drop oversized enums while keeping the base type) with a
configurable :class:`CompressPolicy`. It is implemented independently rather than by
importing the private ``_minimize`` helper because the transforms differ in kind:
descriptions are policy-controlled instead of always dropped, ``anyOf``/``oneOf``
const-unions are collapsed to ``enum``, and ``properties``-style name maps are
recursed by value so a *property named* ``title`` or ``description`` is never
mistaken for a documentation key.

SEMANTIC-SAFETY GUARANTEE
    Compression never changes ``type``, the set of ``properties`` names,
    ``required``, or the structure of ``items``. Every instance that validates
    against the original schema also validates against the compressed schema.
    The only validation change permitted is *widening*: an enum longer than
    ``CompressPolicy.max_enum`` is dropped entirely (keeping the base type)
    rather than truncated, because a truncated enum would silently *reject*
    values the server accepts — for tool-calling, over-restricting the model
    is worse than under-restricting it (mirrors ``minimal_schema`` behavior).
    One narrow exception to "never changes": when a collapsed const-union's
    enum is itself dropped for being oversized, the members' shared ``type``
    is added to a node that had none, so the node is not left unconstrained;
    this too only widens what the schema accepts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from mcp_checkup.models import ToolInfo
from mcp_checkup.serialize import serialize
from mcp_checkup.tokens import count_tokens

DESCRIPTION_POLICIES = ("none", "first-sentence", "full")

# First-sentence descriptions are hard-capped at this many characters.
FIRST_SENTENCE_MAX_CHARS = 120

# Keys that are documentation, not structure; always dropped from schema nodes.
_DROP_KEYS = frozenset({"title", "examples", "default", "$comment", "$schema", "deprecated"})

# Keys whose value maps *names* to subschemas; the names themselves must never
# be treated as schema keywords (a property may legitimately be called "title").
_NAME_MAP_KEYS = frozenset({"properties", "patternProperties", "$defs", "definitions"})


@dataclass
class CompressPolicy:
    """How aggressively to compress.

    ``descriptions``:
        - ``"none"``: drop all descriptions (schema-level and tool-level).
        - ``"first-sentence"``: keep up to the first period, capped at
          :data:`FIRST_SENTENCE_MAX_CHARS` characters.
        - ``"full"``: keep descriptions unchanged.
    ``max_enum``:
        Enums longer than this are dropped entirely (base type kept); see the
        module docstring for why they are not truncated in place.
    """

    descriptions: str = "first-sentence"
    max_enum: int = 10


def _check_policy(policy: CompressPolicy) -> None:
    if policy.descriptions not in DESCRIPTION_POLICIES:
        raise ValueError(
            f"unknown descriptions policy {policy.descriptions!r}; "
            f"expected one of {DESCRIPTION_POLICIES}"
        )


def _first_sentence(text: str) -> str:
    """Up to and including the first period, capped at FIRST_SENTENCE_MAX_CHARS."""
    text = text.strip()
    end = text.find(".")
    sentence = text if end == -1 else text[: end + 1]
    return sentence[:FIRST_SENTENCE_MAX_CHARS].rstrip()


def _apply_description_policy(text: str, policy: CompressPolicy) -> str | None:
    """Description per policy; ``None`` means drop the key."""
    if policy.descriptions == "none":
        return None
    if policy.descriptions == "full":
        return text
    return _first_sentence(text)


def _collapse_const_union(members: Any) -> tuple[list[Any], Any | None] | None:
    """Collapse ``anyOf``/``oneOf`` members that are all const literals.

    Returns ``(enum_values, shared_type_or_None)`` when every member is a dict
    of the shape ``{"const": X}`` or ``{"const": X, "type": T}`` with the same
    ``T`` throughout; returns ``None`` (no collapse) otherwise. The collapsed
    ``{"enum": [...]}`` accepts exactly the same instances as the union.
    """
    if not isinstance(members, list) or not members:
        return None
    values: list[Any] = []
    types: set[Any] = set()
    all_typed = True
    for member in members:
        if not isinstance(member, dict) or "const" not in member:
            return None
        if not set(member).issubset({"const", "type"}):
            return None
        values.append(member["const"])
        if "type" in member:
            types.add(member["type"])
        else:
            all_typed = False
    if len(types) > 1:
        return None
    shared_type = next(iter(types)) if all_typed and types else None
    return values, shared_type


def _compress_node(node: Any, policy: CompressPolicy) -> Any:
    """Recursively compress *node*, treating dicts as schema nodes."""
    if isinstance(node, list):
        return [_compress_node(item, policy) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    collapsed_type: Any | None = None
    for key, value in node.items():
        if key in _DROP_KEYS:
            continue
        if key == "description" and isinstance(value, str):
            kept = _apply_description_policy(value, policy)
            if kept is not None:
                out[key] = kept
            continue
        if key in _NAME_MAP_KEYS and isinstance(value, dict):
            # Values are subschemas; keys are user-chosen names and must be
            # preserved verbatim (never confused with schema keywords).
            out[key] = {name: _compress_node(sub, policy) for name, sub in value.items()}
            continue
        if key in ("anyOf", "oneOf") and "enum" not in node:
            collapsed = _collapse_const_union(value)
            if collapsed is not None:
                enum_values, shared_type = collapsed
                # The enum alone is equivalent to the union; no "type" is added
                # so existing structure is preserved. Remember the shared type in
                # case the enum is dropped below for being oversized.
                out["enum"] = enum_values
                collapsed_type = shared_type
                continue
        out[key] = _compress_node(value, policy)

    enum = out.get("enum")
    if isinstance(enum, list) and len(enum) > policy.max_enum:
        # Drop, don't truncate: a truncated enum would reject values the
        # server accepts. The base "type" (if any) still constrains the model.
        del out["enum"]
        if "type" not in out and collapsed_type is not None:
            # A dropped const-union would otherwise leave the node unconstrained;
            # the members' shared type is a strictly widening replacement.
            out["type"] = collapsed_type
        if policy.descriptions != "none":
            shown = ", ".join(json.dumps(v, ensure_ascii=False) for v in enum[: policy.max_enum])
            note = f"Values include {shown} (+{len(enum) - policy.max_enum} more values accepted)."
            existing = out.get("description")
            out["description"] = f"{existing} {note}" if existing else note
    return out


def compress_schema(schema: dict[str, Any], policy: CompressPolicy) -> dict[str, Any]:
    """Return a compressed copy of *schema*. Pure: *schema* is never mutated.

    Transforms applied recursively:

    - drop ``title``, ``examples``, ``default``, ``$comment``, ``$schema``,
      ``deprecated``;
    - handle every ``description`` per ``policy.descriptions``;
    - collapse ``anyOf``/``oneOf`` unions of const literals into an ``enum``;
    - drop enums longer than ``policy.max_enum`` entirely, keeping the base
      type, with a "(+N more values accepted)" description note unless the
      descriptions policy is ``"none"``.

    SEMANTIC-SAFETY GUARANTEE: ``type``, ``properties`` names, ``required``,
    and ``items`` structure never change, and no instance accepted by the
    original schema is rejected by the compressed one (see module docstring).
    """
    _check_policy(policy)
    return _compress_node(schema, policy)


def compress_tool(tool: ToolInfo, policy: CompressPolicy) -> ToolInfo:
    """Return a new :class:`ToolInfo` with description and schema compressed.

    The tool-level description follows ``policy.descriptions`` (``"none"``
    yields an empty string, since the wire format requires the field).
    """
    _check_policy(policy)
    description = _apply_description_policy(tool.description, policy)
    return replace(
        tool,
        description=description if description is not None else "",
        input_schema=compress_schema(tool.input_schema, policy),
    )


def savings(tool: ToolInfo, policy: CompressPolicy) -> tuple[int, int]:
    """(before, after) estimated token counts of *tool* on the Anthropic wire."""
    before = count_tokens(serialize(tool, "anthropic"))
    after = count_tokens(serialize(compress_tool(tool, policy), "anthropic"))
    return before, after
