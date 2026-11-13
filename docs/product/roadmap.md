# Conversion roadmap

[Documentation index](../README.md)

Status: engine/operations/local-interface delivery priorities updated on 2026-11-14;
historical V1/V2 checkboxes are preserved.
The broader product direction is recorded in [Product vision](product-vision.md).

## Product delivery priorities

These priorities extend [ADR 0002](../decisions/0002-incremental-platform-evolution.md)
with the shared-engine direction in [ADR 0004](../decisions/0004-shared-engine-and-local-interface.md).
They are acceptance gates, not dates or authorization to implement every phase. The product
will expose operations through a local application or VS Code extension; the exact UI choice
remains open. Transformation logic stays in the reusable core and is exercised through API/CLI first.

| Order | Deliverable | Dependencies and acceptance gate | Status |
| --- | --- | --- | --- |
| 0 | Preserve the existing conversion foundation | Deterministic notebook analysis/generation, safe publication and default/custom Kedro naming profiles. | Implemented; scope and evidence remain bounded. |
| E1 | Source completeness and graph fidelity | Every parsed statement has a supported destination or blocks conversion. Cross-check task AST/provenance, imports, selected parameter values, catalog relocation and source dependencies. Exercise the first rewrite of a catalog input. | Initial source-accounting/API guard and dataset-graph correction implemented in this increment; arbitrary semantics remain unsupported. |
| E2 | Functional blocks and a structured Python input | Reuse immutable facts; demonstrate one workflow presented as notebook and structured script reaching the same checked Kedro behavior. Derive a small source-independent representation from these actual cases. | Initial bounded slice implemented: explicit-function analysis, linear entrypoint wiring, JSON catalog/scalar parameters, shared generation and checked paired fixture behavior with default/custom profiles. General DAGs, richer I/O and multi-file analysis remain unsupported; no universal ProjectSpec. |
| E3 | Tests delivered with generated projects | Reviewed observable contracts/fixtures, pytest regression generation and fresh-environment bootstrap checks. Preserve missing expectations as explicit gaps; generated tests alone do not validate business intent. | Initial functional-workflow slices implemented: explicit JSON expectations, shipped node/pipeline pytest tests, gaps/negative controls, plus trusted-example wheel installation and CLI bootstrap in fresh environments with a separate CI matrix. Broader comparators, dependency inference/locking and procedural-notebook tests remain outstanding. |
| E4 | Local operation contracts and first interface | Stable typed API/CLI requests/results for implemented tasks, local configuration, plan/diff inspection and explicit execution controls. Prototype a local app or VS Code extension with conversion/audit/profile operations first. | Proposed; UI choice open. Does not depend on completing every future operation. |
| E5 | Existing Kedro project inspection and standardization | Read-only node/pipeline/catalog/config reconstruction, standards diagnostics, reviewable change plans and idempotence tests. Initially generate into a new destination; safe patch application requires its own conflict/ownership contract. | Proposed. |
| E6 | Project creation from prompt and configuration | Convert prompt into reviewed structured requirements, then generate one narrow ML scaffold using the common generation/validation core. Distinguish missing business logic, inferred code and verified behavior. | Proposed; requirements-based acceptance differs from faithful conversion. |
| E7 | Further targets, MLOps and enterprise governance | Validated needs and operation-specific tests; introduce another backend, integrations, portfolio policies or hosting only when justified. | Proposed; no premature backend/service abstraction. |

Independent pilot review, an authorized real notebook and matched comparisons with general coding
agents remain a parallel evidence workstream. Include full-project success, manual corrections,
review effort, failures/unfinished attempts, latency and cost. Actual human review gates the live
whole-notebook model campaign; it does not block deterministic core development. Customer discovery
and broader source/library contracts accompany the relevant slices.

Source accounting and supported graph checks are implemented. E2 now has
[functional inspection](../reference/functional-blocks.md) and a bounded
[linear workflow conversion](../reference/functional-workflows.md), with source-accounted
generation and paired fixture behavior. E3 now has [explicit contracts and shipped regression
tests](../reference/generated-workflow-tests.md), plus an opt-in fresh-environment wheel/bootstrap
check and CI job. Next establish E4 typed operation requests/results and local configuration for
the implemented engine tasks, before selecting a first interface. Optimization retains a separate
acceptance contract.

## Whole-notebook evaluation next gate

A [draft complete synthetic notebook](../evaluation/synthetic-notebook-pilot.md) now exercises
simulation, local CSV catalog loading and generated pipeline equivalence with negative controls.
Its independent human review remains pending; it is not yet an approved whole-notebook LLM
benchmark. The next gate is source/catalog and behavioral-contract review before live model
evaluation. A [human review worksheet](../evaluation/synthetic-pilot-review.md) and
[experiment proposal](../evaluation/whole-notebook-experiment.md) now make those gates concrete.
The latter fixes nine task proposals, one complete-pipeline outcome, durable evidence and
offline failure/replay tests; no live runner or human approval is claimed. Offline harness
development can proceed with explicit draft status, but live evaluation requires recorded approval.
Existing V2 coverage and release-threshold checkboxes remain incomplete.

The [first offline body-batch increment](../evaluation/offline-notebook-body-batch.md) is now
implemented, with complete static preflight, all-slot outcomes and trusted fixed-body execution
on the pilot. No live whole-notebook measurement or release milestone is complete.
A [draft source-binding increment](../evaluation/notebook-source-binding.md) now verifies notebook,
CSV, contract and expected-catalog bytes plus exact deterministic plan/request reconstruction.
Pending review is retained. A [draft durable capture](../evaluation/notebook-body-capture.md) now
persists the binding, exclusive reservations and raw outcomes, with offline static replay and
explicit missing/unfinished inventory. A [draft pipeline worker](../evaluation/notebook-pipeline-worker.md)
now executes a complete statically valid capture after renewed consent, with bounded snapshots,
typed observations and offline behavioral replay/comparison. A [draft artifact API](../evaluation/notebook-pipeline-artifacts.md)
now publishes runtime/comparison evidence with local before/after identities and strict compatible
offline replay. A [human-review evidence API](../evaluation/notebook-human-review.md) now supports
unchecked pending requests and externally declared, operator-accepted contract wrappers. The real
pilot remains pending; no human identity is authenticated or approval invented. A separate
[draft execution ledger](../evaluation/notebook-execution-ledger.md) now reserves attempts before
worker I/O and retains every published or unfinished outcome for one frozen capture/setup.
This is local offline accounting, not the reviewed live campaign collector. A separate
[metadata-only Ollama controls API](../evaluation/notebook-ollama-controls.md) now captures
server-reported identities and selected settings with offline compatibility checks. It does not
verify effective inference options or integrate model calls into the ledger. An
[offline campaign envelope](../evaluation/notebook-campaign-preflight.md) now binds a supplied
reviewed reference and model sample to exact proposed chat bodies, budgets and all-slot capture
inventory. It refuses pending review; synthetic tests do not approve the actual pilot. Next are
actual human review, operator-selected metadata samples and a consent-gated dispatcher consuming
those exact requests with linked execution evidence; no live notebook-generation adapter is added.
Existing roadmap checkboxes are not promoted
by this preparation work.

## V1 roadmap: deterministic foundation

1. [x] Formalize the supported notebook subset.
2. [x] Initialize the Python package and quality tooling.
3. [x] Implement the immutable intermediate representation and serialization.
4. [x] Load and validate notebooks.
5. [x] Analyze cells with Python's AST.
6. [x] Resolve cross-cell dependencies.
7. [x] Plan minimal Kedro-oriented task candidates.
8. [x] Generate a minimal Kedro project skeleton for controlled fixtures.
9. [x] Verify reference fixture equivalence through observable outputs.
10. [x] Add a file-backed CSV fixture with minimal catalog generation.
11. [x] Extract selected literal parameters into Kedro configuration.
12. [x] Generate readable deterministic node names from headings and simple source patterns.
13. [x] Render a reviewable Markdown conversion report.
14. [x] Add a minimal CLI for planning and reporting.
15. [x] Add a CLI command for generating a Kedro project.
16. [x] Report expected CLI failures without stack traces.
17. [x] Validate conversion plans explicitly before CLI generation.
18. [x] Add reviewable conversion diagnostics to plans and reports.
19. [x] Support a simple `StandardScaler` preprocessing pattern.
20. [x] Support simple pandas preprocessing naming patterns.
21. [x] Extract selected literal pandas preprocessing parameters.

## V2 roadmap: LLM-assisted conversion

### Phase 1: planner boundary

1. [x] Introduce a provider-neutral `SemanticPlanner` protocol.
2. [x] Keep the current deterministic planner as the default implementation.
3. [x] Define versioned request and response contracts for semantic suggestions.
4. [x] Add explicit planner selection to the Python API and CLI.
5. [x] Seed a versioned planning evaluation corpus from the reviewed V1 fixtures.

### Phase 2: safe provider integration

1. [x] Implement a fake provider for deterministic prompt, parsing, and failure tests.
2. [x] Add an optional local Ollama adapter without adding an SDK dependency to the core package.
3. [ ] Require explicit consent before sending notebook content to a remote provider.
4. [ ] Define redaction, credential, timeout, retry, cost, and error-reporting policies.
5. [ ] Keep paid and nondeterministic provider tests outside the default CI workflow.

### Phase 3: hybrid planning

1. [ ] Use LLM suggestions for ambiguous naming, classification, and cell grouping.
2. [ ] Propose node code, parameters, datasets, and tests for transformations not covered by deterministic patterns.
3. [x] Merge suggestions only when they are compatible with static dependencies and plan invariants.
4. [x] Preserve source provenance and identify LLM-assisted decisions in the conversion report.
5. [x] Fall back cleanly to deterministic planning when the provider is disabled or fails.

### Phase 4: evaluation and broader coverage

1. [ ] Build a versioned corpus of representative notebooks beyond controlled fixtures.
   The eight-task development corpus provides seventeen behavioral scenarios. A separate fresh
   four-task `v3` corpus adds twelve scenarios for a later, untuned evaluation; broader real-world
   notebook coverage is still required.
2. [ ] Measure plan validity, generation success, behavioral equivalence, review corrections, latency, and cost.
   Behavioral input/output contracts, deterministic comparison reports and approved-reference
   execution are implemented. Statically validated proposal execution is available behind explicit
   consent. Repeated local full-code/body-only measurements report static acceptance, end-to-end
   behavioral results and latency on the development corpus and on the separate four-task v3
   corpus. Whole projects, review corrections, broader coverage and cost remain outstanding.
3. [ ] Compare deterministic and hybrid results on the same corpus.
   Behavioral code artifacts can now compare two provider runs and replay identical raw responses;
   corpus-bound full-code/body-only comparisons enforce matching recorded controls, now exercised
   by repeated same-runtime v3 measurements. Legacy files are not automatically migrated.
   Broader planning and generation comparisons remain outstanding.
4. [ ] Expand deterministic pandas support for `rename`, `replace`, joins, and aggregations.
5. [ ] Add richer catalog formats and schema-aware diagnostics.
6. [ ] Define release thresholds for a supported V2 preview.

V2 is successful when hybrid planning improves useful notebook coverage without weakening the deterministic guarantees: no unreviewed code reaches generation, invalid plans are rejected, generated nodes remain traceable to source cells, and equivalence checks continue to protect observable behavior.

The provider boundary and its trust rules are documented in
[docs/reference/semantic-planning-contract.md](../reference/semantic-planning-contract.md).
The local transport and its loopback-only safety policy are documented in
[docs/guides/ollama-provider.md](../guides/ollama-provider.md).
Safe suggestion assembly and fallback behavior are documented in
[docs/guides/hybrid-planning.md](../guides/hybrid-planning.md).

Compare the deterministic planner with a downloaded local model on the reviewed corpus:

```bash
notebook-to-kedro benchmark tests/fixtures/evaluation/planning/v1 \
  --project-root . \
  --planners deterministic hybrid \
  --ollama-model your-local-model > planning-benchmark.json
```

The versioned JSON report records corpus hashes, structural accuracy, deterministic plan validity,
fallback usage, and wall-clock planning latency. Live Ollama benchmarking is opt-in and remains
outside the default test suite. The report contract and current limitations are documented in
[docs/evaluation/planning-evaluation-corpus.md](../evaluation/planning-evaluation-corpus.md).
