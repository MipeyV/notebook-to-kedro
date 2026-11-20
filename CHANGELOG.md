# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Generated projects now include `conf/local` so default `kedro run` can load its environment.
  They declare Hatchling and explicit wheel package inclusion instead of relying on an implicit
  build backend, and select the CSV dataset extra instead of all pandas connectors.

- Later rewrites of catalog-backed variables now become nodes and receive distinct generated
  dataset versions, preserving catalog input identities. Resolved output-name collisions fail
  before publication. Windows rename refusals 5/32/33 allow at most three attempts with destination
  rechecks; persistent/other errors remain visible and no writes, providers or execution are retried.
- The public Kedro generator now enforces plan validation, rejects keyword task/package names
  and compiles rendered Python without execution. Copied targets cannot escape or overlap
  generated files. Source checks and private staging prevent routine preparation failures from
  exposing a partial final project; existing destinations remain protected by pre-publication
  checks. This is not a concurrent-filesystem lock or a runtime-equivalence guarantee.
- Windows behavioral-worker directory cleanup retries permission errors at most three times.
  Persistent failures log the remaining path without discarding observed outcomes or masking
  execution-body exceptions; other cleanup errors still propagate. No worker/model retry,
  artifact schema, validator, timeout, consent or security-policy change.

### Added

- Added deterministic synthetic credit-default and policy-lapse cases: 4,200/5,040 records,
  data dictionaries, temporal cohorts, missingness/drift, procedural notebooks, local settings
  and explicit ten-test regression contracts. Independent source/Kedro/metric/threshold checks,
  holdout perturbations and score inversions exercise both profiles and runners. Assertion-only
  and raw-catalog-reuse layouts remain blocked fixtures. Measured weak model outcomes are
  retained; no engine guard, runtime dependency or scientific/productivity claim is changed.

- Extended the opt-in generated-project bootstrap from four functional variants to six,
  adding the procedural decision-tree notebook with default/custom profiles. Fresh wheel
  installation, source-free shipped tests and standard Kedro CLI execution share the existing
  harness. A checker-owned sequential CLI observer validates independent memory-only results
  and a deliberate prediction mutation; reports retain runtime identities, hashes, failures
  and unchanged inputs/configuration/source/gaps. CI uploads these reports on Python 3.11-3.13.

- Added opt-in standalone pytest regressions for procedural notebook projects through API,
  `generate --regression-contract` and local settings. A separate bounded contract captures
  pinned CSV fixtures and explicit JSON/numeric/array/pandas observations, binds real graph
  names/profiles and reports missing positive/node/output expectations. Generation stays static;
  default output and functional contracts are unchanged. A three-node synthetic example ships
  five checks; model serialization and arbitrary typed/artifact oracles remain unsupported.

- Added bounded procedural mixed-cell planning without user-defined functions. Leading imports
  and one exact local CSV load have separate ownership; retained business blocks keep original
  statement ASTs/IDs and use the existing renderer. SA008 rejects unsafe order, omitted/duplicate
  catalog reads and independent task graphs. A four-node/five-parameter ML example is validated
  against source behavior with real catalogs, parameters, runners, profiles and Kedro CLI.

- Added optional shared-data policy 1.0 on source-ordered workflow schemas 1.2-1.7: explicitly
  declared intermediate references retain identity and mutation order through assign-mode
  datasets. Default single-use, catalog-input and mapping-parameter guards remain unchanged.
  Plans/manifests record producer/consumer bindings in schema 1.7. The frozen shared-buffer case
  now passes unchanged independent acceptance and four supplied tests in a separate follow-up.

- Added regression schema 1.2 with explicit inline/fixture storage and supplied concrete built-in
  exception/literal-message expectations. Pipeline cases bind failures to a declared node and
  require no final JSON output; setup/registry failures stay outside expected-error contexts.
  Existing 1.0/1.1 formats remain compatible. A new clipping-notebook run passes its original 14
  shipped tests and independent mutation/runtime acceptance, preserving historical records.

- Added preserved if/for/while, raise/pass and loop break/continue inside functional helper
  bodies, with conservative definite-local bindings and BL104 runtime-path warnings. Keep one
  final value return, original helper ASTs and strict named-call entrypoint wiring. The clipping
  notebook converts and its 12 JSON tests pass; source exceptions are independently verified.
  Generated exception tests and mutable fan-out remain outside this increment.

- Added regression schema 1.1 with SHA-pinned scenario JSON fixtures: retain 64 KiB manifests,
  bound fixtures to 1 MiB/file and 8 MiB total, capture immutable text and publish standalone
  hash-checked fixture tests. Existing inline 1.0 behavior stays compatible. The eight-step
  comparison case now passes all 27 supplied tests in a new fixture-backed run; control flow,
  fan-out, typed/file-reference and artifact expectations retain their earlier limits.

- Extended the prepared comparison with three frozen boundary cases and all blocked tool attempts.
  External agent projects passed independent AST/behavior/threading/error/identity/test/mutation
  checks; oversized regression fixtures, helper control flow and shared mutable fan-out still block
  this engine. Preserve actual outcomes without weakening budgets or claiming faster conversion.

- Preserved a data-only three-case prepared coding-agent comparison corpus and portable prompts.
  Both methods passed matched independent behavior/threading/CLI/test/mutation checks on an ML
  notebook, ordered join and local package/resource. Aggregate observations retain corrections,
  supported-subset scope and separate production/acceptance timing; no engine API or human saving.

- Added API/CLI preparation of prospective effort comparison kits: pending tool/manual/general-
  assistant forms, shared criteria/source/setup fields, machine snapshot and collection guidance.
  Complete stable generation records and a new sibling destination are required; inventory is
  rechecked before shared-writer publication. Prepared a local three-case static pilot, with human
  collection and real productivity evidence still pending.

- Recorded one external frozen-prompt coding-agent check against the deterministic converter on
  a prepared synthetic two-node functional task. Both passed independent runtime/test/mutation
  acceptance; retained failures and different timing boundaries. No provider transport, human
  saving or general notebook-conversion claim is added.

- Added opt-in local-operation timing and conversion effort summaries through API/CLI. Exclusive
  reservations retain failures/interruption and expose unfinished attempts. Human effort binds to
  the current inventory; matched operator-declared baselines can report separate human/elapsed
  differences, including negative savings and labelled estimates. Original operation envelopes
  and dependency surface stay unchanged. Missing baselines never produce an inferred saving.

- Added a standalone developer paired-trial harness for the narrow naive/one_step validation
  artifact contract. It binds operator declarations to exact definition/provenance/script bytes,
  verifies installed import origins, reserves exclusive attempts and compares decoded Parquet,
  finite independently recomputed MAE/RMSE, metadata and artifact inventories. Added installed
  synthetic mutation/failure/timeout controls and locked test-only PyArrow/editables dependencies.
  A new private worksheet passes real runtime preflight. After explicit user review/consent, its
  real pair completed once per path, matched exact scoped expectations and retained 18 artifacts
  each with protected postflight identities intact. Detailed outputs stay private; broader
  coverage, visual equivalence and scientific predictive-quality thresholds remain unverified.

- Documented a provenance-bound paired validation trial with fixed candidate/phase, direct
  application versus registered-pipeline observations, explicit metric/table/artifact checks,
  comparator controls and retained failure evidence. Prepared a private real-source worksheet;
  review, execution consent, the harness and actual benchmark results remain pending.

- Application-aware workflow generation publishes a schema 1.0 byte inventory. A new
  capture-workflow-provenance API/CLI binds the explicit original source Git context, package/
  project/input copies, listed generated bytes and selected-interpreter distribution versions.
  It recomputes prepared adapter lineage, rejects drift/overlap/overwrite and publishes a new
  provenance report with separate execution-directory Git and pending review/runtime status.
  Added original/prepared installed-wheel coverage, Git-context and mutation controls, a private
  authorized real-project capture and indexed ADR 0018.

- Preparation schema 1.1 selects an original application project and preserves its metadata,
  additional files and pyproject-relative source layout alongside the proposed adapter. Manifest
  schema 1.1 binds original distribution facts and prepared paths. Added static recapture,
  collision/deduplication checks, application review instructions and a synthetic preparation
  example that converts through workflow schema 1.7. Standard/editable-wheel installation tests
  exercise metadata, delivered regressions and Kedro CLI behavior after preparation. ADR 0017
  records the composition and review boundary.

- Opt-in workflow schema 1.7 captures an explicitly selected application pyproject, static
  dependency/extras/script declarations and selected project files. Generation stages the original
  application layout under application/ for separate installation and declares its exact
  distribution requirement in the generated Kedro package. Plan/manifest schema 1.6 binds metadata
  and file hashes, with pending build/resolution statuses. Added drift/collision guards, generated
  setup instructions, trusted standard/editable-wheel installation and regression/CLI checks,
  local/VS Code previews and indexed ADR 0016. Read-only real-source capture records declarations
  and the outstanding adopted-entrypoint/runtime review requirements.

- Opt-in workflow schema 1.6 binds declared runtime artifact destinations to exact flat-parameter
  fields and their consuming calls. Generated registered-pipeline adapters check project policy,
  actual values and new targets without rewriting business code, precreating/reserving directories
  or retrying/cleaning application writes. Plan/manifest schema 1.5 records ownership and runtime/
  effect gaps. Added bounded policy markers, source-ordered synthetic JSON/raw-file input cases,
  typed results, partial-failure controls, local/VS Code previews and indexed ADR 0015. Legacy
  behavior, core dependencies, actual execution consent and pending human review remain unchanged.

- Opt-in workflow schema 1.5 supports the explicit `memory` target for a named final result.
  Assign-mode retention keeps the original Python object in the same-process Kedro catalog
  without JSON/pickle coercion or a result filepath. Plan/manifest schema 1.4 records mode,
  persistence and unverified type/artifact status. Added typed synthetic result identity,
  nonpersistence, exception and JSON-failure controls plus local/VS Code previews and ADR 0014.
  JSON targets remain available; typed generated comparators and durable artifacts stay separate.

- Opt-in workflow schema 1.4 adds explicit file-reference inputs with declared sibling sidecars.
  Contained regular-file guards and bounded raw hashing feed the existing copy writer; staged
  path strings reach unchanged application loaders through assign-mode memory datasets.
  Plan/manifest schema 1.3 records inventories/destinations and unverified domain/runtime status.
  Added synthetic sequential/threaded identity and sidecar controls plus local/VS Code previews.
  Existing JSON regression contracts reject undefined file fixtures and report explicit gaps.
  Final result persistence and application artifacts remain separate work; core dependencies
  and legacy workflow behavior stay unchanged. Added indexed ADR 0013.

- Separate explicit orchestration preparation API/CLI previews declared calls against observed
  local functions, or publishes a new raw package copy plus a synthesized forwarding adapter.
  Original/proposed facts remain separate and unreviewed; shared wiring checks retain signatures,
  single-use values and source order. Added immutable bounded definitions, trusted identity/order/
  exception and subsequent Kedro regression checks, ADR 0012 and proposed typed-I/O/artifact gates.
  No source mutation, inferred persistent I/O, application execution or UI schema change.

- Opt-in functional schema 1.3 preserves one explicitly declared regular Python package,
  including original source bytes, import context and resources. Bounded static inventories
  and drift checks feed the existing writer; generated wheels include the original package.
  Supporting modules remain opaque, with dependencies/distribution metadata not reconstructed.
  Added synthetic real-Kedro, pipeline-regression and unpacked-wheel checks, ADR 0011 and
  VS Code 0.2.1 copy previews. Existing source-only inspection/standalone generation remain available.

- Opt-in functional workflow schema 1.2 supports independent calls and joins while preserving
  source call order through explicit ordering-only dependencies. Original functions, business
  wrapper arguments and node regression cases remain unchanged. Plans/manifests record the
  new ordering metadata; schemas 1.0/1.1 retain their linear guard. Added paired synthetic
  examples, threaded/sequential execution and exception controls, and ADR 0010.

- Opt-in functional workflow schema 1.1 supports flat scalar-valued candidate mappings with
  immutable storage, fresh JSON exports and single-use node consumption. Regression overrides
  follow the selected workflow schema; scalar-only schema 1.0 stays compatible. Added paired
  synthetic generation/Kedro/pytest examples and a guide separating a real workflow proposal
  from unresolved independent-loader, package, typed-I/O and artifact contracts.

- Functional inspection schema 1.1 records terminal return expressions without inventing
  output names. Called functions/helpers can retain direct calculations and calls in generated
  Kedro projects under the existing body/dependency guards. Explicit named entrypoint wiring
  remains required; schema 1.0 functional structure fingerprints must be recomputed.

- Added the VS Code 0.2 setup assistant for source/project selection, optional profile and
  expectation files, Python-validated settings creation and immediate inspection. Functional
  inspection now accepts settings before workflow I/O is defined. Planning/generation require
  that contract explicitly. Canceled setup preserves project files and existing settings.

- Added an initial VS Code extension with native Explorer controls for local configuration
  and interpreter selection, static inspection, read-only file previews and destination-confirmed
  generation. The TypeScript adapter calls the existing Python CLI with bounded isolated
  processes. Includes locked tooling, transport/real-host checks, VSIX packaging and CI artifacts.

- Added explicit local JSON settings and immutable inspect/plan/generate operation contracts
  for the existing deterministic notebook and functional workflow engines, exposed through
  Python and `project` CLI actions. Actual rendered file/copy previews perform no writes;
  publication recomputes current inputs and retains the staging writer's no-overwrite checks.
  Root-relative configuration/catalog handling, path guards and explicit execution/install
  gaps prepare a shared interface boundary without a UI, provider or code execution service.

- Added an opt-in trusted functional-example bootstrap check: four script/notebook and
  default/custom variants, fresh wheel installation, source-free shipped pytest/Kedro CLI
  execution, actual runtime identities/hashes and retained logs/JUnit evidence. A separate
  Linux CI matrix targets Python 3.11/3.12/3.13 without adding network checks to offline pytest.

- Functional projects can ship standalone pytest node/pipeline regressions from an explicit,
  bounded JSON expectation contract selected through CLI/API. Immutable expectations,
  profile-aware bindings, temporary test workspaces and a gap snapshot preserve missing oracles
  and separate expectations from execution/review evidence. Subprocess tests and deliberate
  code/oracle/path regressions exercise emitted assertions. Runtime dependencies and procedural
  conversion schemas are unchanged; richer comparators and wider fixture coverage remain future.

- Explicit linear functional workflows now generate Kedro projects from scripts or notebooks:
  versioned JSON I/O/scalar-parameter configuration, recomputed source accounting, reviewable
  plans/manifests, preserved helper functions and assignment-mode intermediate identity. New
  `plan-workflow`/`generate-workflow` commands and Python APIs reuse the extracted Kedro renderer,
  existing profiles and private-staging writer. Paired real-Kedro fixture tests check ordering,
  persistence, expected results and mutable identity. General DAGs, multi-file reconstruction,
  richer formats, fresh dependency installation and generated-project tests remain outstanding.

- Analysis-only explicit functional blocks from structured Python files and real notebook code
  cells, with immutable source/provenance, interfaces, function-reference edges, diagnostics and
  JSON API/CLI inspection. Includes paired examples with matching static fingerprints; script
  generation, data wiring and behavioral equivalence remain the next E2 slice. ADR 0005 records
  the boundary; existing notebook conversion contracts and runtime dependencies are preserved.

- Initial recomputed source-accounting audit with per-statement destinations and source/plan
  identities, plus AST/provenance/import/catalog/parameter/dependency checks. High-level notebook
  planning blocks unsupported or omitted instructions; direct generation can opt in with supplied
  `source_facts`. Existing facts/plan/artifact schemas and fully accounted plan bytes are preserved.
- Shared-engine/operations/local-interface roadmap and ADR 0004. Future app/VS Code choice stays
  open; Python input, project test generation, prompt-driven creation and safe project patches
  remain future operations rather than empty framework abstractions.
- Initial versioned Kedro architecture profiles for a single pipeline name and function/node
  prefix, with strict declarative JSON, CLI/API selection, compatibility diagnostics, review
  mappings and an opt-in generated manifest. Default output remains byte-identical; dataset,
  parameter and body semantics are preserved. Includes a reusable example and complete draft-pilot
  regression with real CSV loading; no human approval, live model call or general policy engine.
- Aligned product vision and delivery priorities for existing-project transformation and future
  greenfield generation, reusable enterprise standards and project-level evidence. Added agent
  conventions and ADR 0002; profiles, shared project specifications and enterprise infrastructure
  remain future work. Existing measurement/review status and the MIT license are unchanged.
- Separate offline notebook campaign preflight: reverified reviewed reference/proof/source bindings,
  selected model metadata, exact proposed chat bodies/options, fixed budgets and exclusive all-slot
  response/error accounting. Interrupted reservations remain visible. No provider dispatch, worker
  execution, actual pilot approval or changes to prompts, validators and existing artifact formats.
- Separate draft notebook Ollama controls API: opt-in metadata-only loopback collection, bounded
  raw response evidence, requested/advertised settings with effective options explicitly unknown,
  exclusive offline publication and strict selected-identity compatibility checks. The new collector
  bypasses environment proxies and rejects redirects/reported remote models. No inference, model
  download, actual pilot approval, ledger/provider reconfiguration or historical-artifact migration
  is introduced.
- Separate draft notebook execution ledger: frozen capture/observation/expectation/budget setup,
  exclusive pre-worker reservations, linked artifact publication and all-attempt offline summaries.
  Unfinished attempts remain visible without inferred crash status or retries. No live collection,
  fixture approval, authenticated audit log, OS sandbox or conversion-default change.
- Separate human-review evidence API for complete notebook references: pending unchecked requests,
  exact source/reference/expectation identities, local proof-file binding, strict declared reviewer/
  worksheet gates and explicit operator-accepted reviewed-contract wrappers. No authenticated human
  identity, real fixture approval, legacy corpus migration, code execution or model calls are claimed.
- Separate draft complete-notebook execution artifacts: exclusive bounded publication, exact raw/
  static/runtime/comparison evidence, before/after local runtime identities, read-only inspection
  and consent-gated compatible offline replay. Unknown controls and observed drift block replay;
  pending review, conversion defaults, historical measurements and provider behavior are unchanged.
- Separate consent-gated draft notebook pipeline worker: bounded source/project snapshots, full
  statically validated DAG execution, typed JSON observations, explicit draft comparison and fresh
  offline behavioral replay. No model calls, approval, OS sandbox or default generator changes.
- Separate offline draft notebook-body capture: persisted source/plan/request binding, exclusive
  reservations and raw response/error publication, incomplete inventory inspection and source-bound
  static replay. No model calls, approval, worker, CLI or historical corpus-format changes.
- Read-only draft notebook source binding for complete body batches: exact notebook/CSV/contract/
  expected-catalog identities, pending-review provenance, frozen requests and exact deterministic
  reconstruction. Rejects source drift, inconsistent catalog metadata, root escapes and altered
  bindings before response validation. No approved contract, persistence, provider or execution API.
- Source-binding regressions and integration with the trusted fixed-body pilot pipeline; existing
  unbound APIs, deterministic conversion, source fixtures and historical model artifacts are unchanged.
- Offline notebook body-batch API with complete plan/graph/import/parameter-evidence preflight,
  exact recorded response/error retention, all planned slots, byte-bounded parsing and
  all-or-nothing static module assembly. No provider calls, execution, persistence or fallback.
- Trusted fixed-provider pilot checks, including complete nine-node execution with the actual
  CSV catalog and every observable expectation, plus failure/missing-slot rejection tests.
  Human review remains pending; no live runner, durable notebook artifact or model result is claimed.
- Pending synthetic-pilot human review worksheet with source/catalog checks, hand calculations
  and approval evidence, plus a proposed whole-notebook LLM experiment with fixed nine-node
  boundaries, complete-pipeline denominators, durable evidence and offline acceptance gates.
  Documentation only; no human approval, runner, model call or conversion-default change.
- Draft synthetic whole-notebook pilot with seeded clients, edge-case local orders, hand-specified
  source/catalog/task/output expectations and explicitly pending independent human review.
  Tests real Jupyter execution and nine generated Kedro nodes using the actual CSV catalog,
  intermediate schemas/rows, splits, predictions and segment metrics, plus six negative controls.
- Test-only CSV connector dependency matching the generated project's existing datasets 8.x
  target. Its pandas constraint resolves the development lockfile to pandas 2.3.3 instead of 3.0.5;
  core dependencies, generator behavior, model prompts, validators and historical corpora are unchanged.
- Categorized documentation index, with product, guides, reference, evaluation and experiment
  folders. The root package README remains in place and is shortened; its detailed overview,
  project status and unchanged roadmap are preserved in product documents. Offline tests check
  local links/headings, index coverage and the root README metadata contract. No runtime changes.
- Product vision and staged roadmap for faithful reproduction, industrialization and explicit
  end-to-end optimization, including contract-adapted templates, source/catalog interpretation,
  enterprise tracking profiles, KPI/segment evaluation, MDL-inspired complexity and repository
  boundaries. Documentation only; no supported-feature, dependency or conversion-default change.
- Opt-in durable behavioral response capture for full-code, corpus-bound full-code and node-body
  runs: complete corpus/metadata manifests, exclusive request reservations and exact raw/provider-error
  publication before validation/execution. Includes `--capture-dir`, `capture-info`, Python APIs and
  offline `recover` with exact-corpus checks and renewed consent. Partial captures are not scored;
  existing artifact schemas, prompts, validation, model retries and conversion defaults are unchanged.
- Capture regressions for interruption, write failure, duplicate calls, corruption and recovery;
  real-worker reference recovery on all twelve v3 scenarios in each of the three formats, without LLMs.
- Documented twelve complete same-runtime full-code/body-only v3 runs, twelve offline replays
  and fifteen comparisons: both body paths and general-model full code pass 4/4 nodes and
  12/12 scenarios; code-model full code rejects an omitted assertion at 3/4 and 9/12.
  Includes exact provenance, raw evidence hashes, repeatability, an initial Windows cleanup
  interruption and limits on generalization, without prompt/validator/default changes.
- Opt-in `bound-full-code` benchmark/replay envelope capturing the complete corpus before
  generation, with strict source/scenario/raw-response validation and exclusive artifact writes.
- Dedicated `compare-formats` API/CLI for corpus-bound full code versus body-only evidence,
  requiring exact corpus, configuration and recorded runtime controls, consistent summaries
  and full scenario denominators. Replay latency deltas are null; legacy files are not migrated.
- Offline comparison regressions and real subprocess reference/archive/replay verification on
  all twelve fresh v3 scenarios, without model calls or prompt/validator/default changes.
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
