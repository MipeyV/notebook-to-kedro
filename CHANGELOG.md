# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Standalone fresh `v3` node/behavioral corpus with four disjoint task notebooks, twelve scenarios
  and eight negative controls for imported helpers, Unicode normalization, branching, stateful
  loops and multiple outputs. Includes pinned identity, static/source checks, negative-control
  sensitivity and real subprocess reference/body-benchmark/replay verification, without model
  calls, prompt/validator changes or edits to measured `v1`/`v2` fixtures.
- Documented six local body-only model runs, six offline replays and thirteen comparisons on
  the unchanged eight-node, seventeen-scenario development corpus: stable 7/8 nodes and 16/17
  matches for `qwen3:8b`, and 8/8 and 17/17 for `qwen2.5-coder:7b`. Includes exact provenance,
  artifact hashes, the general model's parameter-fidelity rejection and historical-runtime caveats;
  no prompt, validator, corpus or conversion-default change.
- Explicit `--proposal-format node-body` selection for behavioral benchmark CLI run/replay/compare,
  preserving full-code defaults and requiring renewed consent for execution.
- Body-only artifact comparison with envelope revalidation, exact corpus/source and execution
  compatibility, outer artifact identities, rejection diagnostics, complete summaries and metadata.
  Replay proposal latency is non-comparable; mixed legacy/body comparisons are rejected.
- Body-only benchmark/replay Python API with a distinct versioned artifact envelope, raw and
  parsed bodies, accepted assembled responses, explicit rejection statuses, corpus identity,
  prompt/assembly/evidence provenance and exclusive atomic publication. Replays regenerate
  assemblies and behavioral outcomes without Ollama; full-code artifact formats remain unchanged.
- Body benchmark regressions and real subprocess benchmark/replay verification for all eight
  approved reference nodes and seventeen scenarios, without live model calls.
- Opt-in `OllamaNodeBodyProvider`, separate `node-body-v1` prompt and provider-neutral
  `request_node_body` service with mandatory exact parameter evidence and strict deterministic
  assembly. Accepted results retain raw JSON, parsed bodies, full responses and prompt/assembly
  provenance; full-code modes and conversion defaults remain unchanged.
- Offline body-provider transport, preflight, fidelity and failure tests, including all eight
  approved reference bodies and a pinned prompt digest, without live model calls.
- Separate versioned `NodeBodyResponse` contract and JSON schema, with an offline AST assembler
  that supplies exact signatures, referenced permitted imports and terminal returns before
  unchanged strict validation. No repair, execution, provider call or automatic project writing.
- Body-contract regressions and compatibility checks for all eight reviewed node references and
  seventeen consent-gated behavioral scenarios; existing full-code providers remain unchanged.
- Archived statement-retention prompt experiment with a reproducible candidate revision, live
  measurements and offline replays for both local models. The regressive `v5` candidate was not
  retained; active prompts `v1`/`v4`, parameter evidence, schemas and the strict validator are unchanged.
- Prompt regression digests and source-data checks covering standalone expressions, calls and
  assertions in both provider modes.
- Controlled local `qwen2.5-coder:7b` comparison on the unchanged `v2` corpus, prompt and validator:
  three runs and an offline replay each accepted 7/8 nodes and matched 16/17 scenarios. The split
  node improved over `qwen3:8b` without observed regressions; conversion defaults remain unchanged.
- Repeated local `qwen3:8b` measurements on independent dataset `v2`: three runs and an offline
  replay each accepted 6/8 nodes and matched 15/17 scenarios end to end. Published per-task results,
  timings and provenance without committing raw model artifacts or changing prompts and validators.
- Expanded independent dataset `v2` with eight node references, seventeen behavioral scenarios and
  seventeen static negative controls. New cases cover aggregation, joins, categorical encoding and
  date features; the measured `v1` baseline is preserved unchanged.
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
- Explicit deterministic or local Ollama-backed hybrid planner selection in the Python API and both
  CLI workflows, with validated provider settings and deterministic defaults.
- Versioned comparative planning benchmark reports with corpus source identities, structural
  metrics, plan-validity and fallback rates, planner latency, and a deterministic CLI export.
- Independent node-code corpus schema and loader with four held-out notebook tasks, manually
  reviewed references, nine known-invalid proposals, source hashes, static dimension metrics,
  detected-error counts and explicit false-rejection counts.
- Versioned behavioral-comparison contracts with five reviewed scenarios, immutable scalar/JSON,
  array and table values, expected exceptions, explicit comparator policies, strict JSON parsing
  and validation against independent node interfaces.
- Isolated execution of approved behavioral references with static revalidation, temporary working
  directories, filtered environments, timeouts, process-group termination, bounded JSON and text
  output, typed execution reports, and explicit failure categories.
- Deterministic exact, numeric, array and table behavioral comparators with expected-exception
  matching, actionable per-output diagnostics, versioned case reports and aggregate corpus metrics.
  All five approved reference scenarios match.
- Explicitly authorized execution of statically validated node-code proposals through the same
  bounded subprocess path, followed by deterministic comparison and a versioned evaluation report
  containing the exact response SHA-256. Process separation remains fault containment, not an OS
  sandbox.
- Versioned provider-to-behavior benchmark reports with separate node acceptance, evaluated-match
  and end-to-end scenario rates, explicit not-evaluated counts, failure categories and provider and
  execution durations. An initial local `qwen3:8b` run matched 3/5 scenarios end to end.
- Reproducible behavioral benchmark artifacts with raw responses, canonical integrity hashes,
  runtime and Ollama provenance, atomic exclusive writes, offline revalidation and execution, and
  CLI comparison of acceptance, behavioral regressions and live-provider latency.

### Planned

- Optional local LLM providers and hybrid semantic planning.
- Versioned code-generation and review datasets.

### Changed

- Node-code validator `node-code-validation-v4` extends whole-body AST preservation to tasks
  without parameters, rejecting unplanned statement additions, omissions, changes and reordering.
  Formatting and comments remain flexible; equivalent refactorings require later behavioral review.
- Node-code validator `node-code-validation-v3` now requires exact planned substitutions and
  unchanged remaining body AST for parameterized tasks, independently of the provider prompt.
  Ambiguous or unsupported parameter mappings fail closed. This is static fidelity checking,
  not runtime equivalence; request and response schemas remain `1.0`.

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
