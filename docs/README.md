# Documentation

[Repository README](../README.md)

The root README is the short introduction, installation and quick start. This index is the
entry point for detailed documentation. Documents are grouped by purpose, not creation date.

## Reading paths

- **Use the tool:** start with the repository quick start, then compatibility, hybrid planning
  and the local Ollama guide if needed.
- **Understand or extend the core:** read architecture, the MVP contract, notebook facts,
  semantic planning and the node-code/body contracts.
- **Evaluate proposals:** read the behavioral comparison contract, select a corpus, then use
  the benchmark and capture/replay guides. Consult measured experiments separately.
- **Plan the product:** read the detailed project status, conversion roadmap and product vision.

## Status conventions

**Reference/guide** documents describe boundaries or workflows; their stated scope and
limitations still apply. **Snapshot** and **measured** documents record evidence for particular
corpora and runtimes, not general accuracy. **Roadmap**, **proposal** and **original design**
documents contain future work. **Rejected experiment** documents preserve unsuccessful evidence.
The compatibility policy is authoritative for supported runtimes and library-support levels.

## Product

| Document | Status | Purpose |
| --- | --- | --- |
| [Project overview](product/overview.md) | Original design | Context, intended interfaces, scope and principles extracted from the old README. |
| [Detailed project status](product/project-status.md) | Reviewed: 2026-11-14 | Current capability matrix, implemented APIs and historical measurement context. |
| [Conversion roadmap](product/roadmap.md) | V1 completed; V2 ongoing | Existing milestones and checkboxes, without changing completion claims. |
| [Product vision](product/product-vision.md) | Direction; future features proposed | Existing-project and greenfield entrypoints, reusable enterprise standards, evidence and commercial hypotheses. |

## Guides

| Document | Purpose |
| --- | --- |
| [Kedro architecture profiles](guides/kedro-profiles.md) | Versioned JSON conventions, default/custom generation, compatibility and source mappings. |
| [Hybrid planning](guides/hybrid-planning.md) | Supported suggestions, assembly and deterministic fallback. |
| [Local Ollama provider](guides/ollama-provider.md) | Provider setup, Python usage and loopback safety boundary. |
| [Body-only Ollama provider](guides/ollama-node-body.md) | Body-generation API, provenance and limitations. |
| [Durable response capture](guides/response-capture.md) | Capture, inspect and recover evidence without new model calls. |
| [Release process](guides/releasing.md) | Prepare versions, tags and GitHub release artifacts. |

## Reference

| Document | Purpose |
| --- | --- |
| [Architecture](reference/architecture.md) | Components, dependency direction, API boundaries and testing strategy. |
| [Compatibility policy](reference/compatibility.md) | Runtime targets, supported patterns and explicit exclusions. |
| [MVP contract](reference/mvp-contract.md) | Initial analysis scope, accepted/rejected constructs and diagnostics. |
| [Notebook facts schema](reference/notebook-facts-schema.md) | Source facts, provenance and interchange representation. |
| [Semantic planning contract](reference/semantic-planning-contract.md) | Requests, suggestions, validation and trust boundaries. |
| [Node code contract](reference/node-code-contract.md) | Full-code proposals, static fidelity checks and provider API. |
| [Node body contract](reference/node-body-contract.md) | Body-only responses and deterministic function assembly. |
| [Exact parameter evidence](reference/node-parameter-evidence.md) | Supported source-expression substitutions and their evidence. |
| [Behavioral comparison contract](reference/behavioral-comparison-contract.md) | Observable values, comparators, execution and consent boundaries. |
| [Source accounting](reference/source-accounting.md) | Statement destinations, AST/catalog/parameter/dependency checks and high-level conversion enforcement. |
| [Functional block inspection](reference/functional-blocks.md) | Analysis-only explicit functions from Python/notebook inputs, source provenance, dependencies and supported-subset diagnostics. |
| [Functional workflow to Kedro](reference/functional-workflows.md) | Explicit linear entrypoints, JSON I/O/scalar parameters, source accounting, generation and paired execution evidence. |
| [Tests delivered with functional projects](reference/generated-workflow-tests.md) | Explicit expectations, standalone pytest tests, gaps/negative controls and opt-in fresh-environment wheel/Kedro bootstrap evidence. |

## Evaluation

These documents define corpora and protocols. Some also retain earlier observations; consult
the dedicated experiment reports for their frozen settings, decisions and limitations.

| Document | Purpose |
| --- | --- |
| [Planning evaluation corpus](evaluation/planning-evaluation-corpus.md) | Reviewed planning cases, structural metrics and benchmark CLI. |
| [Independent node-code corpus](evaluation/node-code-evaluation-corpus.md) | Hand-authored references, source binding and negative controls. |
| [Fresh node corpus v3](evaluation/fresh-node-corpus-v3.md) | Four additional tasks, twelve scenarios and independent controls. |
| [Synthetic whole-notebook pilot](evaluation/synthetic-notebook-pilot.md) | Simulation plus real CSV catalog loading, full-workflow checks and negative controls; human review pending. |
| [Synthetic pilot review](evaluation/synthetic-pilot-review.md) | Pending human checklist, hand calculations and explicit approval evidence. |
| [Whole-notebook experiment](evaluation/whole-notebook-experiment.md) | Full experiment proposal: review gates, frozen controls and opt-in nine-node LLM measurement; no live runner. |
| [Offline notebook body batch](evaluation/offline-notebook-body-batch.md) | Implemented recorded-response static preflight/assembly and trusted pilot execution; no live runner. |
| [Draft notebook source binding](evaluation/notebook-source-binding.md) | Read-only file hashes, deterministic reconstruction and drift rejection; human review stays pending. |
| [Draft notebook body capture](evaluation/notebook-body-capture.md) | Exclusive request/raw-outcome inventory and offline static replay; no model calls or worker. |
| [Draft notebook pipeline worker](evaluation/notebook-pipeline-worker.md) | Consent-gated complete DAG execution, typed observations and offline behavioral replay/comparison; review pending. |
| [Draft notebook pipeline artifacts](evaluation/notebook-pipeline-artifacts.md) | Exclusive execution/comparison reports, runtime identities, offline inspection and compatible consent-gated replay; review pending. |
| [Notebook human review evidence](evaluation/notebook-human-review.md) | Pending requests, externally declared review proofs and explicit operator-accepted contract wrappers; no automatic fixture approval. |
| [Draft notebook execution ledger](evaluation/notebook-execution-ledger.md) | Pre-worker reservations, exclusive linked outcomes and all-attempt offline accounting, including unfinished attempts; no live campaign runner. |
| [Draft notebook Ollama controls](evaluation/notebook-ollama-controls.md) | Opt-in metadata-only samples, raw evidence, requested/advertised/unknown effective settings and offline identity compatibility; no inference. |
| [Offline notebook campaign preflight](evaluation/notebook-campaign-preflight.md) | Reviewed evidence, exact proposed chat requests/budgets and exclusive all-slot capture accounting; no dispatcher or inference. |
| [Node code benchmark](evaluation/node-code-benchmark.md) | Static acceptance, AST fidelity and historical prompt/validator experiments. |
| [Behavioral code benchmark](evaluation/behavioral-code-benchmark.md) | Consent-gated execution, observable comparisons and archived runs. |
| [Body-only benchmark and replay](evaluation/node-body-benchmark.md) | Body artifacts, replay and compatible comparisons. |
| [Generation format comparison](evaluation/generation-format-comparison.md) | Corpus-bound full-code versus body-only comparison controls. |

## Experiments

| Document | Status | Purpose |
| --- | --- | --- |
| [Local code-model comparison](experiments/local-code-model-comparison.md) | Measured | Controlled full-code comparison on the eight-task development corpus. |
| [Statement-retention prompt](experiments/node-code-statement-retention.md) | Rejected experiment | Preserved evidence for the regressive v5 candidate. |
| [Body-only model measurements](experiments/node-body-local-measurements.md) | Measured | Repeated body runs and replays on the development corpus. |
| [Fresh v3 format measurements](experiments/fresh-v3-format-measurements.md) | Measured | Same-runtime repeated comparisons on four fresh tasks. |

## Decisions and history

- [ADR 0001: use uv](decisions/0001-use-uv.md): accepted dependency-management decision.
- [ADR 0002: incremental platform evolution](decisions/0002-incremental-platform-evolution.md):
  shared-core direction, two entrypoints and the bounded generation-reliability milestone.
- [ADR 0003: minimal Kedro profiles](decisions/0003-minimal-kedro-profiles.md): deterministic
  naming/organization, opt-in adoption and preservation of computational contracts.
- [ADR 0004: shared engine and local interface](decisions/0004-shared-engine-and-local-interface.md):
  reusable operation core, future local app/VS Code surfaces and the first source-accounting slice.
- [Agent instructions](../AGENTS.md): development conventions, verification and project memory.
- [Changelog](../CHANGELOG.md): release-facing changes.
- [Development journal](../JOURNAL.md): chronological work, decisions and unresolved questions.
- [ADR 0005: explicit functional block inspection](decisions/0005-explicit-functional-block-inspection.md):
  analysis first, honest Python/notebook origins and a later generation/behavior increment.
- [ADR 0006: linear functional workflow generation](decisions/0006-linear-functional-workflow-generation.md):
  explicit wiring, preserved call order/object identity and reuse of the Kedro renderer/writer.
- [ADR 0007: explicit generated regression tests](decisions/0007-explicit-generated-regression-tests.md):
  supplied oracles, standalone tests, explicit gaps and separate execution evidence.

## Maintaining documentation

- Keep the root README short and usable without reading internal contracts.
- Choose a folder by purpose and add every new document to this index.
- Link detailed documents back to this index and distinguish implemented scope from proposals.
- Keep measurements bound to their original corpus/runtime; do not rewrite them as new accuracy.
- Update inbound and outbound links when moving a document, including fragments.
- Keep historical evidence and roadmap completion states intact during navigation changes.
- Maintain vision, architecture, status and roadmap in their existing documents; record
  significant approved decisions in ADRs rather than duplicating journal history.
- Run the offline navigation checks with `uv run pytest -o addopts= tests/unit/test_documentation.py`.

The 2026-10-11 reorganization changes document paths on the current branch. Earlier commits
and release tags retain their old paths. Use this index for current navigation; external
bookmarks to the old flat `docs/` layout need updating after merge.
