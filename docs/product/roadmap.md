# Conversion roadmap

[Documentation index](../README.md)

Status: completed V1 milestones and ongoing V2 roadmap, extracted on 2026-10-11.
Checkboxes retain their previous state; this reorganization does not complete milestones.
The broader product direction is recorded in [Product vision](product-vision.md).

## Current next step

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
on the pilot. Next are notebook/review identity binding, durable evidence and a consent-gated
whole-pipeline worker/replay. No live whole-notebook measurement or release milestone is complete.

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
