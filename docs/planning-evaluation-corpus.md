# Planning Evaluation Corpus

## Purpose

The planning corpus is the reviewed reference for comparing deterministic and future
LLM-assisted semantic planners. It evaluates the transformation from deterministic
`NotebookFacts` to task structure. It does not evaluate generated node code; code generation and
review will use separate datasets so planning and implementation errors remain distinguishable.

The initial `v1` corpus contains four controlled notebooks and 26 expected tasks. It establishes a
regression baseline but is not a representative benchmark of real-world notebook diversity.

## Storage

Cases are stored as one reviewable JSON document per notebook under:

```text
tests/fixtures/evaluation/planning/v1/
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

Future real-world cases must also record provenance, usage rights, and any redaction applied before
notebook code is committed or sent to a model provider.
