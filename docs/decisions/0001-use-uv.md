# ADR 0001: Use uv for Python project management

- **Status:** Accepted
- **Date:** 2026-08-17

## Context

Notebook to Kedro needs reproducible local development and CI environments while keeping published dependencies separate from tooling, notebook fixtures, Kedro integration tests, and future optional LLM providers.

The project also needs a committed cross-platform lockfile, Python version selection, editable installation, build commands, and a consistent command interface.

## Decision

Use uv as the project and dependency manager.

The repository will contain:

- `pyproject.toml` for package metadata, build configuration, dependency constraints, and tool configuration;
- `uv.lock` for exact reproducible resolution;
- `.python-version` for the primary local Python version;
- `.venv/` as the local uv-managed environment, excluded from Git.

Published runtime dependencies use `[project.dependencies]`. User-facing optional integrations use `[project.optional-dependencies]`. Local tooling uses standardized `[dependency-groups]` grouped by purpose.

CI will install dependencies with:

```bash
uv sync --locked
```

Commands will run through uv:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

The package will use Hatchling as a lightweight PEP 517 build backend. uv manages the project environment and build invocation but is not itself the build backend.

## Consequences

### Positive

- Local and CI environments resolve from the same lockfile.
- Runtime, optional, test, lint, and development dependencies remain explicit.
- Contributors use one command family for syncing, running, locking, and building.
- The `src/` package is installed in editable mode during development.
- Lockfile drift can be rejected in CI.

### Trade-offs

- Contributors must install uv.
- Some tools may not yet understand dependency groups directly, although uv does.
- Generated Kedro projects need their own environment and lockfile; they must not reuse the converter's environment implicitly.
- Dependency updates require intentional lockfile maintenance.

## Alternatives considered

### pip and requirements files

Widely available, but separating published constraints from multiple development groups and maintaining reproducible cross-platform resolution requires additional tools and files.

### Poetry

Provides project and lockfile management but introduces a separate metadata and command model where standard `pyproject.toml` fields and uv dependency groups are sufficient for this project.

### PDM

A capable standards-based alternative. uv was selected for its fast resolver, Python management, standardized dependency-group support, and simple CI workflow.
