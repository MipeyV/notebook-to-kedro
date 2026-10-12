# Draft notebook source binding

[Documentation index](../README.md)

Status: implemented **read-only, in-memory draft binding** for the
[offline body batch](offline-notebook-body-batch.md). No provider calls, artifact persistence,
code execution, human approval or live whole-notebook benchmark is introduced.

## What is bound

`create_notebook_source_binding` takes a supplied deterministic plan, project root, draft contract
and expected-catalog path. It records exact SHA-256 values and byte sizes for:

- The entire contract JSON, including task boundaries, expectations and review provenance.
- The notebook, checked against its declared contract hash and path.
- The caller-selected expected catalog file, without treating its YAML as approved configuration.
- Every local CSV declared in the contract and connected to a catalog input in the plan.

The binding also freezes the complete declared plan, request prefix, ordered task requests,
canonical review JSON and snapshot-byte limit. `content_sha256` identifies all those fields,
excluding itself. `NotebookSourceFile` paths are resolved project-relative paths; escaping the
project root is rejected before reading the file, including paths whose resolution leaves it.
Only regular files are accepted; directories and other filesystem entry types are refused.

File identity means exact bytes, not semantic JSON/CSV equivalence: even a whitespace or newline
change invalidates an existing binding. Identical bytes with changed modification times do not.
The notebook and CSV hashes must match their contract declarations. Contract/catalog hashes are
captured from the supplied files, not inferred from a generated project or hard-coded globally.

## Source and plan checks

The API reuses complete static batch preflight, then rebuilds the supplied plan using the existing
notebook loader, AST analyzer and deterministic planner with the explicit project root. It requires
exact plan equality, including imports, boundaries, interfaces, catalog, parameters and diagnostics.
Renaming or editing a plan manually is rejected even if its new body could pass node validation.
Hybrid/grouped plans are deliberately outside this first binding contract.

Contract parsing is limited to the draft's source/provenance envelope. It rejects duplicate JSON
keys, non-finite JSON numbers, invalid source hashes, inconsistent catalog declarations, duplicate
source names and unbound catalog inputs. Simulation stays a node output without a file or catalog
entry. Only `simulation` and `local_csv` source descriptions are supported; no Kaggle, sklearn-loader,
Spark/Databricks or cloud connector is added. Other contract fields are covered by the full-file
hash, **not** semantically validated or independently approved by this API. The pilot's existing
runtime tests still check the business tables, catalog behavior and negative controls.

Every measured file is rechecked after reconstruction to detect observed changes during preparation.
Each explicit snapshot read is guarded by a positive integer `max_file_bytes`, default `16,777,216`.
This is a per-file snapshot guard, not a total process-memory, filesystem or worker budget. The
existing loader performs its own reads. There is no cross-file atomic snapshot or filesystem lock;
these checks are point-in-time drift detection, not protection against hostile concurrent mutation.

## Review boundary

Only `pilot-draft-1` with explicit `pending`, `independent_human_review: false` and
`reviewed_by: null` is accepted. Original authorship and local-provider exposure metadata are
retained, not inferred from tests or a merge. This API cannot promote a draft by flipping a flag.
Approval requires a real human review record and a separately specified reviewed contract upgrade.
See the [review worksheet](synthetic-pilot-review.md).

Hashes prove neither trusted authorship nor the correctness of expectations. A new explicit binding
can be created for a revised draft after its declarations and plan are made consistent, but this is
not human approval and does not turn that draft into an approved benchmark or execution permission.

## Python API

```python
from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import (
    create_notebook_source_binding,
    validate_source_bound_notebook_body_batch,
    verify_notebook_source_binding,
)

root = "."
plan = plan_notebook_path(
    "tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb",
    project_root=root,
)
binding = create_notebook_source_binding(
    plan,
    project_root=root,
    contract_path="tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json",
    expected_catalog_path="tests/fixtures/evaluation/pilots/customer_churn_v1/expected_catalog.yml",
    request_prefix="attempt-1",
)
verify_notebook_source_binding(binding, project_root=root)
# Missing responses remain nine planned slots, without provider calls or execution.
report = validate_source_bound_notebook_body_batch(binding, (), project_root=root)
print(binding.content_sha256, report.batch.planned_count, report.batch.static_ready)
```

For recorded `NotebookBodyRecord` values, pass their sequence instead of `()`. Use
`binding.requests` as the exact request inventory. The wrapper verifies binding integrity and
recreates current source/plan/request evidence **before** calling static response validation.
Missing, changed or oversized files, stale contract/catalog metadata and modified bindings fail
with `ValueError`; no response parsing, repair or deterministic fallback follows that failure.
Other existing loader/analysis errors still propagate. Recomputing a cached binding hash alone
does not bypass reconstruction. Direct unbound batch APIs remain available with their earlier scope.

The returned `SourceBoundNotebookBodyReport` contains the binding and ordinary static `batch`.
`static_ready` still does not mean runtime equivalence or execution consent. The binding has an
experimental draft version. A separate [draft capture API](notebook-body-capture.md) now persists
the complete binding and raw outcomes and verifies them against an explicitly supplied binding.
It adds reservation inventory and static replay, not reviewed-contract or behavioral execution support.

## Verification and next step

Offline tests cover all four file roles, deletion, byte drift, metadata/schema failures, bounded
reads, root escapes, reconstruction changes and internally rehashed but inconsistent bindings.
They verify responses are not processed after source drift, and observed changes during static
reconstruction are rejected. The complete trusted-body pilot test now obtains its nine requests
from this binding, verifies it before static assembly and matches all notebook/contract observables
through the actual CSV catalog. This is locked-runtime fixture compatibility, not a model result.

```bash
uv run --locked --python 3.12 pytest -o addopts= \
  tests/unit/evaluation/test_notebook_sources.py \
  tests/integration/test_synthetic_notebook_pilot.py
```

Next: build on the separate draft capture layer with a dedicated
consent-gated worker with bounded immutable input snapshots and network-free replay. Recheck source
identity before future I/O/execution gates; this in-memory binding does not lock files between them.
Live measurement remains gated by human review and the remaining
[whole-notebook protocol](whole-notebook-experiment.md).
