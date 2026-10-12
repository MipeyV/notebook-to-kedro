# Draft notebook pipeline worker

[Documentation index](../README.md)

Status: implemented **offline, consent-gated complete-pipeline execution and comparison** for
the draft [captured body batch](notebook-body-capture.md). Human review remains pending.
No model is called, no user project is patched, and no reviewed-contract or live measurement
is introduced. This is a separate evaluation path; the default converter is unchanged.

## Gates and lifecycle

`run_notebook_pipeline_capture` first requires `allow_untrusted_code_execution=True`, including
on every replay. It then rechecks current source identity and the saved capture, validates the
explicit observation inventory and reruns the unchanged body parser/assembler/AST validator.
Observations must uniquely name planned task outputs; parameters and unknown datasets are refused.

One missing, provider-failed, malformed or statically rejected body leaves `execution=None`.
There is no subprocess, partial pipeline, replacement node, retry or fallback. The static report
retains every planned request. Capture completeness is not static acceptance or runtime success.

For a complete valid batch, the parent reads bounded source snapshots and checks exact identities.
It renders the existing deterministic project into a private temporary directory, redirects CSV
copying to those snapshots and substitutes only the validated assembled node module. Generated
catalog bytes must exactly match the bound expected catalog. Sources are reverified after preparation.
Neither source notebooks nor proposed modules are imported or executed by this parent path.

The bounded JSON request carries source/project bytes as base64 plus individual SHA-256 identities,
the requested observations and frozen node wiring. The worker verifies the request byte digest and
file identities, materializes its own contained project, imports the generated registry, verifies
node names/input/output wiring and runs the complete DAG using `OmegaConfigLoader`, the real CSV
`DataCatalog` and `SequentialRunner`. Node outputs are observed before normal dataset release.

Snapshot bytes are frozen in the request, not OS-immutable files. Copies isolate normal pipeline
I/O from changing original CSV paths; concurrent source changes observed during preparation fail.
This does not lock source files atomically or prevent hostile code from modifying its private copies.

## Limits and outcomes

The API reuses `BehavioralExecutionConfig`, with notebook defaults:

| Bound | Default |
| --- | --- |
| Complete worker timeout | 60 seconds |
| JSON request, including all source/project snapshots | 16 MiB |
| Typed JSON result | 4 MiB |
| Retained stdout and stderr | 16 KiB each |

Raw snapshot/project totals are checked during preparation, then the complete encoded envelope is
checked before process start. The child verifies a bounded request read, and both sides enforce
result bounds. Oversized observations have `serialization_failure`; a fallback too large to fit
causes `process_failure`. Result paths must be regular files contained in the private directory.
Missing, corrupt, wrong-identity or wrong-inventory results also have
`process_failure`. The parent checks log byte bounds rather than trusting the child to honor them.

Successful observations, business exceptions, setup failures, timeouts, process failures and
serialization failures remain distinct. Exceptions or observation failures discard partial outputs.
Timeouts reuse existing process-tree termination and temporary-directory cleanup behavior.
No dependency download, fresh installation or separate `kedro run` packaging check is claimed.

`NotebookPipelineRun` records draft version, full capture/static context, configuration, observation
inventory, assembled module digest, exact request digest and optional execution result. Its nested
`BehavioralExecutionResult` is reused solely as typed subprocess transport: `node_code_case_id`
contains the whole capture digest as a correlation identity, **not** a node case or notebook score.
No approved `BehavioralCase` is manufactured and existing node-corpus loaders remain unchanged.

## Observation scope

`NotebookObservation(dataset, kind)` has three adapters:

- `value`: finite scalars, ordered JSON-like lists/objects, typed NumPy arrays and pandas tables.
  Tables retain column order, dtype strings, row order and index values. Missing table cells are
  JSON null with their original dtype retained; infinities and unsupported cell objects are refused.
  This does not distinguish every missing sentinel (`NaN`, `None`, `pd.NA`), index class/name or
  categorical metadata, and is not arbitrary pandas/Spark serialization.
- `series`: a pandas Series observed as a one-column typed table named `value`, preserving values,
  dtype and index order. The original series name is not included.
- `decision_tree`: an exact `DecisionTreeClassifier` summary: class, max depth, random seed,
  fitted classes, training sample count and feature count. This is not a complete fitted-tree
  serialization, estimator equivalence proof or generic model adapter.

Unsupported observations, including a wrong requested adapter, produce serialization failure.
The fitted model stays in the child. The parent receives typed JSON only, never an untrusted pickle.
Result-size bounds are transport limits, not an in-memory object-size or OS resource guarantee.

## Comparison and replay

`compare_notebook_pipeline_run` requires an exact ordered inventory of caller-supplied
`ExpectedBehaviorOutput` values and policies. It reuses existing deterministic value comparators
without creating an approved corpus case. It hashes those expectations and records a separate
outcome for every requested observable. Differences are bounded by the configured capture limit.

If the pipeline was not executed or execution failed, every check is `not_evaluated`, never a
match. A successful result must belong to the statically ready capture and contain every requested
output before comparison. Overall `matched` requires every check to match; one mismatch is enough
for an overall `mismatch`. This is caller-declared draft comparison, not human approval or model
accuracy. The API does not automatically interpret or approve business expectations in contract JSON.

Calling `run_notebook_pipeline_capture` again rereads and statically validates the same saved raw
evidence, requires renewed consent and executes a fresh worker. It makes zero provider calls and
does not trust cached runtime outputs. Request hashes identify bytes, not runtime compatibility.
Use the same locked environment; runtime/hardware/model provenance freezing, persisted execution
reports and campaign accounting remain later gates before live measurement.

```python
from notebook_to_kedro.evaluation import (
    NotebookObservation,
    compare_notebook_pipeline_run,
    run_notebook_pipeline_capture,
)

# binding and draft expectations are supplied explicitly; human review remains pending.
run = run_notebook_pipeline_capture(
    "generated/offline-pilot-capture",
    binding,
    (NotebookObservation("accuracy"),),
    project_root=".",
    allow_untrusted_code_execution=True,
)
comparison = compare_notebook_pipeline_run(run, expectations)
```

## Trust and evidence

The worker is a fresh `python -I` process with the existing filtered environment, discarded native
stdout/stderr and a private working directory. **It is not an OS security sandbox**: same-user code
can access files or network outside that directory and forge observations. Hashes are not
authentication. Sensitive notebooks require operator-managed isolation and storage controls.
No remote-provider consent, secret handling, cloud reader, tracker or privacy policy is added.

Tests use trusted fixed fixture bodies only, including direct private-worker unit tests. The pilot
captures nine bodies, executes and replays the full worker, and compares seventeen table/series/model/
prediction/metric observations against both the source notebook and hand-specified expectations.
All six existing oracle sensitivity controls remain on their trusted test-only path; no mutant is
admitted by weakening AST fidelity. This is locked-runtime reference compatibility, not an LLM result.

```bash
uv run --locked --python 3.12 pytest -o addopts= \
  tests/unit/evaluation/test_notebook_execution.py \
  tests/integration/test_synthetic_notebook_pilot.py
```

Next: bind and publish complete execution/comparison evidence and frozen runtime controls, then
support genuine human-reviewed contract promotion. Live collection still requires those gates and
the remaining [whole-notebook protocol](whole-notebook-experiment.md); no model calls while pending.
