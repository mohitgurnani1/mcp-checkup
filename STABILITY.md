# Stability contract (v1.0)

As of v1.0.0 the following are frozen and governed by semantic versioning —
breaking any of them requires a major version bump:

## CLI

- Commands: `scan` (default), `weigh`, `fix`, `serve`, `diff`
- All documented flags and their defaults
- New flags/commands may be added in minor versions; none removed or
  repurposed

## Exit codes (`scan`)

| Code | Meaning |
| --- | --- |
| 0 | OK |
| 1 | Token budget exceeded (`--fail-over`, `--fail-over-total`) |
| 2 | Hygiene findings at/above `--fail-on-severity` |
| 3 | No configured server was reachable |

## Documents

- Scan JSON (`--format json`): `schema_version: 1`, schema published at
  [schemas/report.v1.json](schemas/report.v1.json). New optional fields may
  appear in minor versions; existing fields never change meaning or type
  within schema_version 1.
- Baseline files (`--write-baseline`): `schema_version: 1`; hashes remain
  sha256 over the compact sorted JSON of name+description+input_schema.
- Badge endpoint JSON: shields.io endpoint schema.

## Not covered by the freeze

- Table/markdown/HTML visual layout (may improve any release)
- Token estimates themselves (tiktoken and provider serialization evolve)
- Hygiene heuristics: new checks may be added and pattern lists refined in
  minor versions; check IDs are stable and `--disable-check` always works

## Deprecation policy

Anything scheduled for removal is announced in release notes and emits a
runtime warning for at least one minor release before a major removes it.
