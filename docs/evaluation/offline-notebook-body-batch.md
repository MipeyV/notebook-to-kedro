# Offline notebook body batch

[Documentation index](../README.md)

Status: implemented **static recorded-response preparation and validation**, plus trusted
fixture execution in tests. This is the first offline increment of the
[whole-notebook proposal](whole-notebook-experiment.md), not its live runner, durable artifact
or consent-gated worker. The [pilot review](synthetic-pilot-review.md) is still pending.
A separate [draft source-binding wrapper](notebook-source-binding.md) now verifies notebook,
CSV, contract and expected-catalog bytes and reconstructs the deterministic plan before this
static API processes records. The direct unbound APIs below retain their original scope.

## Boundary

`prepare_notebook_body_requests` preflights the entire supplied conversion plan before returning
task requests. It validates the plan, dataset graph, statement uniqueness, shared import syntax,
module naming and exact parameter evidence. It does not read a notebook or dataset, call a
provider, write files or execute proposed code. Shared imports are compiled without execution.

The first graph contract requires unique producers across tasks and catalog roots, resolved
dataset inputs and no cycles. It deliberately rejects symbol rebinding across tasks, even where
the V1 renderer can version repeated symbols. Broader version-aware wiring is deferred; the
default converter is unchanged. Node names cannot shadow imports or Python builtins, and
relative/wildcard imports are rejected. These are conservative batch-only restrictions.

`validate_notebook_body_batch` consumes already recorded response strings or transport errors,
not a provider object. It repeats complete preflight, rejects unknown/duplicate record IDs before
parsing, and returns exactly one proposal slot per planned task in plan order. Record input order
may differ. No request retry, response repair, reference-code fallback or partial module is produced.

The caller is responsible for accurate collection history: an absent record is represented as
`not_requested`, not evidence that a provider was never contacted. This transient API cannot
distinguish an unmade request from evidence lost outside it. Durable request reservation and
interrupted-run inventories remain required in the future notebook-bound capture layer.

## Python API

The following validates records already held in memory; it does not acquire or execute them:

```python
from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import (
    NotebookBodyRecord,
    prepare_notebook_body_requests,
    validate_notebook_body_batch,
)

plan = plan_notebook_path("path/to/notebook.ipynb")
requests = prepare_notebook_body_requests(plan, request_prefix="attempt-1")
# recorded_json_by_id is an existing mapping of exact raw strings, not a provider.
records = tuple(
    NotebookBodyRecord(request.request_id, recorded_json_by_id[request.request_id])
    for request in requests
    if request.request_id in recorded_json_by_id
)
report = validate_notebook_body_batch(plan, records, request_prefix="attempt-1")
print(report.accepted_count, report.planned_count, report.static_ready)
```

A transport failure uses `NotebookBodyRecord(request_id, provider_error=(code, message))`.
Exactly one raw string or error is required; empty raw text is retained and rejected as an
invalid response. Embedded response/request/task identities must match, and body assembly
uses the existing strict source-AST validator and exact parameter substitutions unchanged.

Responses are checked against a default `1,048,576` UTF-8 byte parsing limit. A positive integer
`max_response_bytes` can override it. Oversized or invalid-UTF-8 strings are retained with a
distinct rejection code and are not parsed. This is a parsing bound, **not** a transport,
total-memory or capture-size limit: the caller has already supplied the raw strings in memory.

## Results

Each immutable proposal retains its request, exact record, parsed body when valid, accepted
assembled response when valid, status and diagnostic. Statuses distinguish `accepted`,
`not_requested`, `provider_error`, `invalid_response` and `invalid_code`. A valid JSON body with
wrong identity, syntax or source behavior is an invalid-code outcome, not a repaired response.

`planned_count` includes every task; `accepted_count` includes only statically accepted bodies.
`static_ready` is true only when all slots are accepted and a complete `module_source` exists.
That text preserves the supplied plan's shared imports in their original order and includes
all validated functions in plan order. It is not imported, executed or written by this API.
Even a statically ready module remains untrusted; this is not an execution permission or a
runtime-equivalence verdict. Do not import user/model assemblies in the parent process.

The report includes a SHA-256 of canonical JSON for the complete declared plan, including
catalog, parameters, source strings and notebook path. It detects changes to that plan, not
source authenticity, on-disk notebook/CSV changes, human approval or provider provenance.
Absolute paths make it workspace-specific; it is not a relocation-independent corpus identity.
There is no persisted artifact schema, score, live provider entrypoint or notebook CLI yet.

## Offline verification

Unit tests cover complete/missing batches, exact raw retention, unknown/duplicate IDs, response
and byte-limit failures, graph ambiguity/cycles, import collisions and parameter-evidence preflight.
They prohibit execution, network access and project writes during static validation.

Pilot tests use a fixed test-only provider built from the original notebook cells, with the
single explicit planned fill-values substitution. It is a source echo, not an independently
authored gold code oracle or a live model result. All nine calls are recorded once; transport,
JSON, semantic and missing-body failures retain a nine-slot denominator and prevent assembly.

One end-to-end test writes only those trusted fixture assemblies into a temporary generated
project, then runs the real CSV catalog and all nine nodes. Every table, split, model summary,
prediction and metric is compared with both the source notebook and hand-specified expectations.
This reuses the existing pilot oracle and pending-review provenance, not the V1 renderer as
expected behavior. It is test-only locked-runtime compatibility, not an untrusted-code worker,
an arbitrary notebook evaluation or fresh-install/`kedro run` acceptance.

```bash
uv run --locked --python 3.12 pytest -o addopts= \
  tests/unit/evaluation/test_notebook_body.py \
  tests/integration/test_synthetic_notebook_pilot.py
```

Draft notebook/CSV/review identity binding is available in the separate wrapper, and
[durable draft capture](notebook-body-capture.md) now records reservations/raw outcomes and supports
offline static replay. A [draft pipeline worker](notebook-pipeline-worker.md) now adds consent-gated
complete DAG execution, typed observations and behavioral replay/comparison. Next: durable runtime
evidence and frozen controls. Live model
measurement remains gated by recorded human approval and the remaining protocol acceptance tests.
