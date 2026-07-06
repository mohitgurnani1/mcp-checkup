.PHONY: help test lint format precommit check

help: ## Show this help
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

test: ## Run unit tests with coverage
	uv run pytest

lint: ## Run ruff and codespell
	uv run ruff check .
	uv run ruff format --check .
	uv run codespell src tests README.md CONTRIBUTING.md

format: ## Auto-format and fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

precommit: format lint test ## Everything required before opening a PR

check: precommit ## precommit + fail on any uncommitted diff (what CI runs)
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "ERROR: 'make precommit' produced uncommitted changes:"; \
		git status --porcelain; \
		git diff; \
		exit 1; \
	fi
