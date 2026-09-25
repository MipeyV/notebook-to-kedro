# Planning Evaluation Corpus

## Purpose

The planning corpus is the reviewed reference for comparing deterministic and future
LLM-assisted semantic planners. It evaluates the transformation from deterministic
`NotebookFacts` to task structure. It does not evaluate generated node code; code generation and
review will use separate datasets so planning and implementation errors remain distinguishable.

The initial `v1` corpus contains four controlled notebooks and 26 expected tasks. It establishes a
regression baseline but is not a representative benchmark of real-world notebook diversity.

The `semantic-v1` corpus measures whether semantic assistance adds value over that baseline. It
contains four negative controls whose deterministic boundaries must remain unchanged and three
positive grouping challenges. Related statements in the challenge notebooks are deliberately
split across adjacent code cells under explicit Markdown headings. The reviewed plans cover a
basic training workflow, preprocessing with feature scaling, and comparison of two independent
models. Together, the corpus contains seven cases and 47 reviewed logical Kedro nodes.

## Storage

Cases are stored as one reviewable JSON document per notebook under:

```text
tests/fixtures/evaluation/planning/v1/
tests/fixtures/evaluation/planning/semantic-v1/
```

Each document is immutable for a released schema version. Incompatible field changes require a
new versioned directory and schema version.

## Case contract

| Field | Meaning |
| --- | --- |
| `schema_version` | Version of the planning evaluation contract. |
| `case_id` | Stable identifier for the reviewed example. |
| `notebook_path` | Repository-relative source notebook path. |
| `source_sha256` | Hash copied from analyzed notebook metadata. |
| `review_status` | Must be `approved`; unreviewed labels cannot enter the gold corpus. |
| `tasks` | Ordered reviewed task structures. |
| `expected_catalog_datasets` | Ordered catalog dataset names expected in the plan. |
| `expected_parameter_names` | Ordered extracted parameter names expected in the plan. |
| `expected_blocking_diagnostic_codes` | Blocking diagnostics expected for the notebook. |

Each expected task records:

- a stable task label and expected pipeline ID;
- source cell and statement IDs;
- the exact raw source assigned to the task;
- expected node name, inputs, outputs, and parameter references;
- expected source diagnostic codes.

Source boundaries, rather than predicted names or IDs, associate proposed tasks with reviewed
tasks. This lets the evaluator report naming or wiring errors independently from cell-grouping
errors.

## Metrics

`evaluate_planning_case` returns dimension-level metrics:

- task-boundary precision and recall;
- stable task-ID accuracy;
- node-name accuracy;
- raw-source accuracy;
- input, output, and parameter-reference accuracy;
- diagnostic and pipeline-assignment accuracy;
- exact catalog, extracted-parameter, and blocking-diagnostic matches;
- a final exact-match flag.

An exact match requires the reviewed source hash, every task boundary, every task attribute, and
the plan-level expectations to match. A successful parse or plausible node name is not sufficient.

## Adding a case

1. Add a deterministic notebook fixture with no hidden execution state.
2. Analyze it and record the resulting source SHA-256.
3. Review task boundaries and labels manually rather than copying planner output blindly.
4. Add the approved JSON case to the current compatible schema directory.
5. Run the corpus integration test and inspect every changed metric.

Semantic cases must include both positive grouping examples and negative controls. A useful model
must merge reviewed boundaries without over-merging already-correct tasks. The current semantic
contract can only group statements represented by deterministic task candidates; code cells that
produce no tracked output require a separate evidence-model change before they can enter this gold
corpus.

Future real-world cases must also record provenance, usage rights, and any redaction applied before
notebook code is committed or sent to a model provider.

## Benchmark runner

`run_planning_benchmark` analyzes every corpus notebook once, then executes each named planner over
the same immutable facts. Timing covers `SemanticPlanner.create_plan` only; notebook loading and
static analysis are intentionally excluded. Planner names are sorted before execution so result
ordering is stable.

The CLI exposes the same runner and writes a versioned JSON report to stdout:

```bash
notebook-to-kedro benchmark tests/fixtures/evaluation/planning/v1 \
  --project-root . \
  --planners deterministic hybrid \
  --ollama-model your-local-model > planning-benchmark.json
```

Use `tests/fixtures/evaluation/planning/semantic-v1` to measure semantic improvement rather than
baseline reproduction.

`deterministic` is the default when `--planners` is omitted. Hybrid benchmarking requires an
explicit downloaded local Ollama model. The report labels it as `hybrid:<model>` so comparisons do
not lose model identity. Ollama URL and timeout overrides use the same loopback-only validation as
planning and generation.

## Benchmark report

Planning benchmark schema `1.0` records:

- ordered corpus case IDs, notebook paths, and source SHA-256 digests;
- the planner label and planner version returned for every case;
- complete dimension-level `PlanningEvaluation` metrics;
- deterministic plan-validation success;
- semantic fallback usage through diagnostic `SP005`;
- wall-clock duration for every planning call;
- aggregate exact-match, valid-plan, fallback, and latency statistics.

JSON key ordering and planner/case ordering are stable. Measured durations and model responses are
naturally nondeterministic.

This first runner measures planning structure, not generated-code quality. It does not yet execute
generated projects, compare observable outputs, collect reviewer corrections, inspect token usage,
or estimate energy and monetary cost. Those dimensions require separate versioned evaluation
contracts rather than being inferred from task-structure accuracy.
