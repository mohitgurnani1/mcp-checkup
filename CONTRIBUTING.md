# Contributing to mcp-checkup

Thanks for your interest! This project is small and early — good first
contributions are very welcome.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python, venv, and dependencies)
- `make`

## Development workflow

Everything goes through `make`:

```bash
make test       # run unit tests with coverage
make lint       # ruff check + codespell
make format     # ruff format + ruff check --fix
make precommit  # format + lint + test — run before every PR
make check      # precommit, then fails if it produced any uncommitted diff (what CI runs)
```

Optionally install the git hook so this happens automatically:

```bash
uv run pre-commit install
```

## Pull request guidelines

- **Run `make precommit` before opening a PR.**
- **DCO required**: every commit needs a `Signed-off-by` line — use
  `git commit -s` with your real name.
- **PR title** follows Conventional Commits and is checked by CI:
  `<type>: <subject>`, lowercase subject. Allowed types:
  `feat, fix, docs, test, chore, ci, refactor, release`.
- Tests are required for new code paths and bug fixes.
- During review, address comments with new commits — do not force-push or
  rebase while under review. Maintainers squash on merge using the PR title.

## Use of generative AI

AI-assisted contributions are welcome, with conditions:

- You must fully understand and be able to explain and revise everything you
  submit — you own it, not the tool.
- Disclose AI use in the PR description.
- Strip comments or scaffolding that only exist to help an AI navigate the
  code; every comment must be valuable to human readers.

## Questions

Open a [discussion or issue](https://github.com/mohitgurnani1/mcp-checkup/issues).
