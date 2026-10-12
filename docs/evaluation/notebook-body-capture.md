# Draft notebook body capture

[Documentation index](../README.md)

Status: implemented **offline draft evidence and static replay**. No model call, provider
adapter, CLI, proposal execution or approval is introduced. The synthetic pilot's independent
human review remains pending. This is separate from the approved node-corpus
[response capture](../guides/response-capture.md), not a new input accepted by that format.

## Lifecycle

`create_notebook_body_capture` verifies the supplied [source binding](notebook-source-binding.md)
before creating a fresh directory. Its manifest contains the entire plan, ordered requests,
file fingerprints, pending review, binding version/digest, declared provider/model/prompt names,
current validator version and the static response parsing limit. Existing directories are refused.

`reserve_notebook_body_request` exclusively publishes a reservation for an exact frozen request ID.
`record_notebook_body_response` exclusively publishes either its unmodified decoded response string
or its exact provider-error code/message. Both recheck current sources and the existing inventory
first. There are no automatic calls, retries, repairs, fallback bodies or resume loops. A caller
can explicitly finish an existing reservation by publishing its outcome, but cannot reserve it again.

Publication reuses the existing atomic, exclusive JSON writer: temporary file, flush/fsync, then
hard-link publication without overwriting. An I/O or byte-limit failure propagates to the caller;
it never produces a fabricated response, completion marker or success score. Preserve failed
directories for inspection; creation failures are not automatically deleted or reopened.

```text
capture/
  manifest.json
  attempts/<sha256-of-request-id>.json
  responses/<sha256-of-request-id>.json
```

Reservations bind the request ID and canonical manifest digest. Outcomes retain those identities,
the exact string, its SHA-256 and error fields. Response hashes use UTF-8 with `surrogatepass` to
preserve even invalid Unicode strings for subsequent rejection by the existing parser. These are
decoded provider strings, not original HTTP wire bytes. Whitespace and malformed response JSON are
not normalized or repaired. JSON escaping is only the lossless on-disk envelope representation.

## Inspection and replay

`load_notebook_body_capture` requires the caller's explicit verified binding and current project
root. It compares the stored binding canonically, checks schema/validator metadata, strictly decodes
JSON (duplicate fields and non-finite values refused), validates file inventory, reservations,
record identities and raw hashes, and returns records in planned order. It does not deserialize
arbitrary saved plans into execution inputs or import proposed code.

The loaded `NotebookBodyCapture` distinguishes:

- `missing_request_ids`: every planned request without a published outcome.
- `unfinished_request_ids`: reserved requests without outcomes; this is not proof a call occurred.
- `attempted_request_ids`: recorded reservations, not authenticated provider-call history.
- `complete`: all planned outcomes exist, including provider errors; not a successful conversion.
- `content_sha256`: canonical manifest, reservations and ordered decoded records, for snapshot identity.

`replay_notebook_body_capture` reloads and verifies evidence, then runs the existing source-bound
static batch validator under the saved response parsing limit. Missing records retain the full
denominator. That batch's existing `not_requested` label describes absent responses, not definitive
call history: consult the capture inventory to distinguish unfinished reservations. Complete
inventory alone cannot make the batch statically ready; all bodies must pass unchanged validation.
Partial inventories can be inspected and statically replayed but never assemble a complete module.

## Python example

```python
from notebook_to_kedro.evaluation import (
    NotebookBodyRecord,
    create_notebook_body_capture,
    load_notebook_body_capture,
    record_notebook_body_response,
    replay_notebook_body_capture,
    reserve_notebook_body_request,
)

# binding comes from create_notebook_source_binding; its human review is still pending.
directory = create_notebook_body_capture(
    "generated/offline-pilot-capture",
    binding,
    project_root=".",
    provider_name="offline-fixture",
    model_name="trusted-source-echo",
    prompt_version="fixture-1",
)
request = binding.requests[0]
reserve_notebook_body_request(directory, binding, request.request_id, project_root=".")
# A deliberately invalid offline example, saved before proposal parsing.
record_notebook_body_response(
    directory,
    binding,
    NotebookBodyRecord(request.request_id, "not JSON"),
    project_root=".",
)
inventory = load_notebook_body_capture(directory, binding, project_root=".")
report = replay_notebook_body_capture(directory, binding, project_root=".")
assert not inventory.complete
assert report.batch.module_source is None
```

## Limits and trust

- Default per-file envelope read/write limit: 16 MiB; default static response parsing limit: 1 MiB.
  Limits are positive integers. Encoded JSON size includes escaping/metadata and is checked before
  publication; bounded reads stop at limit plus one byte. Oversized raw strings can be retained
  within the envelope limit and rejected later by the smaller parsing limit. These are not
  transport, total-memory or security limits; the caller already holds strings and serialization
  uses memory. Inventory cardinality is restricted to the frozen requests, not arbitrary filenames.
- File paths must resolve inside the capture root and be regular files. Linked inventory
  directories and unknown layout entries are refused. This is not an OS sandbox or hostile-race
  protection; source/inventory checks are point-in-time and do not lock concurrent writers.
- Hashes detect inconsistent stored evidence, not authorship/authentication. A malicious rewrite
  of a consistent entire capture, or deletion of all evidence of an attempt, cannot be proven by
  local hashes alone. Keep captures on trusted storage; do not treat reservations as call receipts.
- Provider/model/prompt identities are caller declarations. Rendered prompts, transport options,
  timing/cost and authenticated call receipts are not captured by this offline API. No claim of a
  live reproducible model measurement is made; those controls are required before a live adapter.
- No credentials, automatic data redaction, cloud loading, fresh installation or model download
  is provided. Raw responses and requests may contain sensitive data; storage is caller-managed.
- Fixture merge and green tests do not approve its business contract. Reviewed-contract promotion
  remains a separate step. Existing historical model measurements and corpus formats are unchanged.

## Verification and next step

Offline tests cover complete/partial/error inventories, publication failures, duplicate reservations,
exact malformed raw strings, bounds, corrupt JSON/metadata/hashes, unexpected paths and source drift
before replay or append. The trusted fixed-body pilot now captures all nine outcomes, verifies static
replay matches direct validation, then executes only those trusted fixture assemblies against the
notebook oracle and real CSV catalog. That test path is not a general untrusted-code worker.

```bash
uv run --locked --python 3.12 pytest -o addopts= \
  tests/unit/evaluation/test_notebook_capture.py \
  tests/integration/test_synthetic_notebook_pilot.py
```

A separate [draft pipeline worker](notebook-pipeline-worker.md) now uses this evidence for
consent-gated execution, typed observations and fresh behavioral replay. A separate
[draft artifact API](notebook-pipeline-artifacts.md) now publishes runtime/comparison reports and
checks local before/after controls for compatible replay. The separate [review evidence API](notebook-human-review.md)
now prepares pending requests and checks operator-accepted wrappers. Next: actual human review and
durable execution/campaign accounting. Live measurements still require human review
and the remaining [whole-notebook protocol](whole-notebook-experiment.md) controls.
