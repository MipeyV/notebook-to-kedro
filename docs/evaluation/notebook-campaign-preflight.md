# Offline notebook campaign preflight

[Documentation index](../README.md)

Status: **offline Python API implemented; no provider dispatcher or live measurement**.
Version: `notebook-campaign-draft-1`. The real synthetic pilot still awaits independent human
review. Positive review declarations and model metadata in unit tests are explicitly synthetic,
not an approval of that pilot or a model-accuracy measurement.

## Frozen evidence

`NotebookCampaignInputs` supplies the source binding and locations of the reviewed wrapper,
reference artifact, reference capture and project root. `prepare_notebook_campaign` reloads the
reviewed contract through the existing strict loader: current notebook/catalog/data identities,
raw reference evidence, behavioral comparison, declared human review and local proof bytes are
rechecked. A pending review, changed reference or changed source fails before campaign creation.
The original `pilot-draft-1` metadata is not edited or promoted in place.

The envelope binds:

- Reviewed-contract, reference-artifact, source-binding and expectation hashes.
- Reference worker-configuration hash; the reference already contains observations and runtime
  evidence. This is not a fresh compatibility check of the current execution environment.
- Exact operator-supplied [Ollama controls](notebook-ollama-controls.md) sample hash, loopback
  endpoint and selected model. Known stable advertised identities are required.
- One ordered request per deterministic task, source-request hash and exact canonical proposed
  chat-body JSON with its byte hash. Prompt/schema/assembly/parameter-evidence/validator versions,
  complete body-response schema,
  parameter evidence, model, messages, `stream: false`, `think: false` and requested generation
  options are frozen. Existing prompts, validators and providers are not modified.
- Provider timeout, byte bounds and one complete-pipeline attempt budget. All planned requests
  remain in the denominator; task count is not notebook success count.

Explicit positive `num_ctx` and `num_predict` are required; the advertised context capacity must
cover the requested context. Requested temperature and optional seed are included exactly as
normalized by the controls API. These are **proposed request options**, not measured effective
options. The old body provider does not consume this envelope; passing it only a model name
would not apply these controls. No inference endpoint is called by this API.

Defaults: 120 seconds per provider request, 1 MiB response-validation limit, 16 MiB per proposed
chat body, 16 MiB per capture file and 32 MiB per envelope file. Capture-file limits may be lowered,
not raised above 16 MiB. Response-validation limits cannot exceed the capture-file limit. Raw
outcomes are retained before parsing, including malformed or over-validation-limit responses if
their serialized evidence fits the capture-file bound. JSON escaping and envelope overhead also
consume storage; publication failure must stop a future dispatcher, not trigger a retry.
The timeout and prediction budget are recorded intent, not an enforced wall-clock limit here.

## Exclusive inventory

`create_notebook_campaign` creates a new directory containing only `manifest.json` and `capture/`.
It refuses existing destinations. The capture uses the existing draft body-capture format without
migrating any historical evidence. `load_notebook_campaign` bounds envelope reads, reconstructs
all frozen fields from supplied current evidence and checks exact capture settings/layout. It
does not trust rehashed derived fields. It revalidates the reference's static evidence, but does
not parse newly captured outcomes, contact HTTP endpoints or execute a worker.

`reserve_notebook_campaign_request` rechecks the envelope and external evidence before reserving
one known request exclusively. `record_notebook_campaign_response` requires that reservation and
publishes either exact raw assistant content or an explicit provider error. It cannot overwrite
an outcome. Neither function invokes a provider, resumes a request or retries a failed operation.
Future dispatch must reserve before provider I/O and persist raw output before parsing.

`notebook_campaign_summary` describes a previously loaded inventory. Every planned slot is
`not_requested`, `unfinished`, `raw_response` or `provider_error`; totals include all reservations
and missing outcomes. A complete inventory can consist entirely of errors or invalid JSON. It is
neither static readiness nor behavioral success. An unfinished reservation does not diagnose a
timeout, crash or running process.

```python
from notebook_to_kedro.evaluation import (
    NotebookCampaignInputs,
    create_notebook_campaign,
    load_notebook_campaign,
    notebook_campaign_summary,
)

# binding and controls are separately verified evidence objects supplied by the operator.
inputs = NotebookCampaignInputs(
    binding=binding,
    reviewed_contract_path="generated/reviewed.json",
    baseline_path="generated/reference.json",
    reference_capture_directory="generated/reference-capture",
    project_root=".",
)
directory = create_notebook_campaign("generated/campaign-001", inputs, controls)
inventory = load_notebook_campaign(directory, inputs, controls)
summary = notebook_campaign_summary(inventory)  # Initially every task is not_requested.
```

## Limits and next gate

This envelope is a local declaration, not an authenticated execution log. Manually recorded
responses do not prove that its exact requests/options were dispatched, that a named model
produced them, or that the server applied requested settings. It does not authenticate the
reviewer's identity/independence or operator approval. Hashes detect inconsistent evidence,
not an adversary rewriting all bytes and hashes. Store source-containing prompts and raw outcomes
privately; ignored directories do not provide encryption or access control.

Reads are not atomic snapshots or filesystem locks. Publication of individual files is exclusive,
but creating the directory and capture is not one transaction. An interruption can leave a
partial directory, which is refused on inspection and must not be overwritten or automatically
resumed. Bounds are per file, not a total disk/memory budget. There is no registry of all campaign
directories: summaries concern the one inspected attempt, not every experiment on the machine.

The [execution ledger](notebook-execution-ledger.md) still manages worker attempts separately
for a frozen capture. This increment does not run or automatically attach that ledger, check a
fresh worker runtime, sample current/post-generation model metadata, collect inference timings,
implement provider/execution consent, or assemble a complete measured campaign report. Static
capture replay and worker execution remain explicit existing APIs, not automatic consequences
of a complete inventory.

Next: an offline-tested dispatcher consuming these exact request bytes, explicit renewed provider
and execution consent, before/after model/runtime checks and linked all-attempt execution evidence.
Real model calls remain blocked until actual independent pilot review is supplied. No changes to
default conversion, historical node benchmarks, fixtures, model selection or release thresholds.
