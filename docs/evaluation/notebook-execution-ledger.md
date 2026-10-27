# Draft notebook execution ledger

[Documentation index](../README.md)

Status: **offline Python API implemented; human review and live collection pending**.
Version: `notebook-execution-ledger-draft-1`. This is draft execution accounting for one
frozen capture, not an approved benchmark, authenticated audit log or live campaign runner.
Conversion defaults, prompts, validation and original pending review metadata are unchanged.

## Frozen setup and reservations

`create_notebook_execution_ledger` requires an existing source binding and raw body capture.
It rechecks source/capture identities and freezes the ordered observation adapters, explicit
typed expectations/comparison policies and execution configuration in `manifest.json`.
Observation names must be unique planned outputs; expectation names must match in order.
Expectations are caller-declared draft values, not inferred or approved business truth.
Creation never parses proposed bodies, starts a worker or contacts a model.

The ledger directory must be new. It contains only the manifest, `attempts/` and `results/`.
Each reservation records the manifest hash, caller-chosen non-empty attempt ID and a canonical
UTC reservation timestamp. Its filename is the SHA256 of the ID, not an interpolated path.
Each result envelope binds the reservation hash to a complete existing
[pipeline artifact](notebook-pipeline-artifacts.md), including runtime and comparison evidence.
All three payloads carry canonical content hashes; hashes are not signatures or authentication.

`run_notebook_pipeline_attempt` requires `allow_untrusted_code_execution=True` before any I/O.
It exclusively publishes a reservation **before** body validation, project preparation or
worker execution. It rechecks the frozen capture through the existing worker API, executes at
most once and publishes the complete result exclusively after validation and comparison.
There is no automatic retry, resume, repair, provider call or cached-output substitution.
Standalone `reserve_notebook_pipeline_attempt` creates only a reservation; it cannot later be
resumed through the run API. A deliberate new execution must use a new identifier.

Exceptions, `KeyboardInterrupt` and publication failures propagate. If reservation publication
completed but result publication did not, that ID remains reserved without a completed report.
Duplicate IDs fail before worker I/O, whether the earlier attempt completed or not.
Source/reservation/setup changes observed before publication block the new result.
The original artifact/replay APIs remain available separately; they do not automatically
register their executions in this ledger. Replayed parent-linked artifacts are not imported as
new ledger attempts. No legacy evidence is upgraded retroactively.

## Usage

```python
from notebook_to_kedro.evaluation import (
    create_notebook_execution_ledger,
    load_notebook_execution_ledger,
    notebook_execution_ledger_summary,
    run_notebook_pipeline_attempt,
)

# Binding, capture, observation adapters and expectations were prepared offline.
directory = create_notebook_execution_ledger(
    "generated/pilot-ledger",
    binding,
    capture_directory,
    observations,
    expectations,
    project_root=".",
)
attempt = run_notebook_pipeline_attempt(
    directory,
    binding,
    capture_directory,
    "offline-attempt-1",
    project_root=".",
    allow_untrusted_code_execution=True,
)
ledger = load_notebook_execution_ledger(
    directory,
    binding,
    capture_directory,
    project_root=".",
)
summary = notebook_execution_ledger_summary(ledger)
```

Default worker configuration is unchanged: 60 seconds, 16 MiB request, 4 MiB result and
16 KiB captured logs. A custom `BehavioralExecutionConfig` can be supplied at creation and is
then frozen. The original worker still enforces the strict static and typed-output gates.

## Inspection and denominators

Loading requires the explicit binding and original capture directory. It rechecks current
sources, full raw capture, exact manifest/reservations and every result. The artifact decoder
reconstructs static evidence and comparisons; an envelope hash alone is insufficient.
`notebook_pipeline_artifact_from_dict` exposes that same reconstruction for structured nested
artifacts; unlike file readers, it expects an already decoded object and applies no byte limit.
Inspection does not execute proposed code, launch workers or contact providers.

| Attempt status | Meaning |
| --- | --- |
| `unfinished` | A reservation exists without a published result. It may be running, interrupted or failed before publication; the reader cannot infer which. |
| `static_rejected` | A published artifact records no assembled module or worker execution. Missing/provider-error/invalid-body slots remain in its full static report. |
| `matched` / `mismatch` | A successful typed worker outcome was compared to the frozen expectations. |
| `exception`, `timeout`, `setup_failure`, `process_failure`, `serialization_failure` | The existing worker returned this typed failure; behavioral comparisons remain not evaluated. |

The summary reports every reserved ID, total reservations, published results, unfinished count
and status counts. A matched outcome never removes failed or unfinished attempts from this
denominator. Ordering is by hashed filename for deterministic inspection, not chronological order.
The summary is not a model-accuracy score, review decision or comparable-runtime certification.
Runtime identities remain in each artifact; later controlled comparisons must enforce compatibility.

## Bounds and trust

Serialized manifest/reservation/result files default to at most 64 MiB each, with bounded
limit-plus-one reads and exclusive atomic publication using the existing JSON writer. Strict
JSON rejects duplicate keys and non-finite constants; unexpected entries, malformed files,
orphan results, changed identities and results for another setup fail inspection, not silently
disappear. Default inspection and reservation admission are limited to 1,000 attempts; inspection
can choose another positive bound. These are per-file/count bounds, not an aggregate memory,
disk, execution-budget or multi-process admission-control guarantee.

This is a local, single-operator workflow, not a transactional database. Independent concurrent
writers, reads during publication and filesystem replacement races are not coordinated. Checks
are point-in-time; source sampling is not a lock. A hard crash during atomic file publication can
leave a temporary file; unexpected leftovers fail closed and need operator investigation rather
than automatic deletion or a fabricated completed result. Directory metadata is not fsynced;
no universal power-loss durability claim is made.

A same-user adversary can delete reservations, rewrite/re-hash all evidence, forge timestamps
or fabricate worker observations. This is not an append-only secure log or an OS sandbox.
Operator isolation, storage access and sensitive-data policies remain necessary.

Trusted offline tests retain unfinished reservations, typed failures and actual nine-node pilot
execution with seventeen matched observables. They do not approve the pilot or measure a model.
A separate [metadata-only Ollama controls API](notebook-ollama-controls.md) now records selected
model advertisements and identity compatibility without inference. This ledger does not yet bind
those controls or approve a model campaign. An [offline campaign envelope](notebook-campaign-preflight.md)
now binds a supplied reviewed reference and model sample to exact proposed requests and all-slot
capture inventory; it does not run or automatically attach this ledger. Next gates are actual
review, operator-selected samples and a consent-gated dispatcher with linked execution evidence.
Keep all registered attempts visible there too.
