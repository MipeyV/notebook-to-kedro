# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Provider-neutral `SemanticPlanner` protocol with an injectable deterministic implementation.
- Versioned planning evaluation contracts, dimension-level metrics, and a reviewed four-notebook
  V1 corpus.
- Versioned semantic planning request and response contracts, a structured-output JSON schema,
  invocation trace metadata, and strict validation against deterministic V1 evidence.
- Deterministic semantic prompt rendering, a provider transport protocol, a configurable fake
  provider, and explicit fallback to the V1 plan for expected provider or response failures.
- Loopback-only Ollama structured-output transport using the standard library, with bounded
  responses, configurable timeouts, normalized failures, and no core SDK dependency.
- Hybrid semantic planner assembly for safe task renaming and adjacent grouping, with static
  interface reconstruction, parameter preservation, report provenance, and deterministic fallback.

### Planned

- Optional local LLM providers and hybrid semantic planning.
- Versioned code-generation and review datasets.

## [0.1.0] - 2026-09-22

### Added

- Deterministic notebook loading and validation for supported Python notebooks.
- AST-based extraction of statements, symbols, calls, reads, writes, and diagnostics.
- Cross-cell dependency resolution with stable source provenance.
- Immutable, versioned `NotebookFacts` and `ConversionPlan` contracts.
- Deterministic task planning with readable names derived from Markdown headings and
  recognized source patterns.
- Reviewable plan diagnostics and explicit validation before project generation.
- Markdown conversion reports covering tasks, datasets, parameters, and diagnostics.
- CLI commands for reviewing a plan and generating a minimal Kedro project.
- Minimal Kedro nodes, pipelines, registry, catalog, parameters, and project files.
- CSV-backed catalog generation and source-data copying.
- Literal parameter extraction for selected scikit-learn and pandas operations.
- Support for a simple `StandardScaler` workflow and selected `dropna`, `fillna`, `assign`,
  and `drop(columns=...)` preprocessing patterns.
- End-to-end fixtures comparing observable notebook and generated Kedro outputs.
- Python 3.11, 3.12, and 3.13 CI coverage with strict linting, typing, and test coverage.

### Known limitations

- The release targets reasonably clean, sequential notebooks rather than arbitrary notebook
  code.
- Generated projects support a narrow, documented subset of pandas and scikit-learn.
- Catalog inference is currently limited to simple CSV-backed inputs.
- Dynamic execution, hidden interactive state, unsupported side effects, and ambiguous
  transformations produce diagnostics instead of speculative conversions.
- LLM-assisted planning and code generation are not included in this release.

[Unreleased]: https://github.com/MipeyV/notebook-to-kedro/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MipeyV/notebook-to-kedro/releases/tag/v0.1.0
