# Draft notebook pipeline artifacts

[Documentation index](../README.md)

Status: **offline Python API implemented; independent human review and live measurement pending**.
This format is `notebook-pipeline-artifact-draft-1`, separate from approved node-corpus artifacts.
It does not change conversion defaults, fixture approval, prompts or historical measurements.

## Evidence and publication

`run_notebook_pipeline_capture` now records runtime identities before preparation/execution and
after the outcome, including statically blocked batches. `create_notebook_pipeline_artifact`
requires these contemporaneous identities; it cannot silently fill them from a later environment.
It retains the complete source binding and raw capture, every static slot, observation adapters,
execution limits, assembled-module/request hashes, typed worker outcome and explicit expected
values/comparison policies. The comparison is recomputed, not supplied as an approval claim.

Partial captures, provider errors, rejected bodies, worker failures, exceptions and mismatches
remain visible. Missing execution means `not_evaluated`, never `matched`. The pending review
metadata stays pending. Business expectations are caller-declared draft values, not automatically
approved or inferred from the contract file. No whole-notebook model score is introduced.

`write_notebook_pipeline_artifact` uses exclusive atomic publication and refuses replacement.
Default serialized-file limit is 32 MiB, checked before publication; reads use a limit-plus-one
bounded read and strict JSON with duplicate-key/non-finite-constant rejection. A canonical SHA256
binds the complete payload. Existing oversized/incomplete/corrupt files are never overwritten.

Publication is an explicit step **after** execution. This increment does not reserve an execution
attempt before starting the worker. A crash before publication leaves no complete runtime report;
saved request reservations/raw responses remain in the capture. Durable campaign accounting and
interrupted execution-attempt inventory are still separate future work.

```python
from notebook_to_kedro.evaluation import (
    create_notebook_pipeline_artifact,
    load_notebook_pipeline_artifact,
    replay_notebook_pipeline_artifact,
    write_notebook_pipeline_artifact,
)

# run was produced with explicit execution consent; expectations remain draft.
artifact = create_notebook_pipeline_artifact(run, expectations)
write_notebook_pipeline_artifact("generated/pilot-execution-1.json", artifact)
inspected = load_notebook_pipeline_artifact(
    "generated/pilot-execution-1.json", binding, capture_directory, project_root="."
)
replayed = replay_notebook_pipeline_artifact(
    "generated/pilot-execution-1.json",
    binding,
    capture_directory,
    project_root=".",
    allow_untrusted_code_execution=True,
)
write_notebook_pipeline_artifact("generated/pilot-execution-1-replay.json", replayed)
```

## Inspection and replay

Loading requires the caller's explicit source binding and original capture directory. It verifies
current source bytes and capture inventory, revalidates every body and the complete module, parses
typed execution/expectation values, and recomputes all comparisons. Rehashed changes to capture,
static evidence or comparison claims still fail against the reconstructed report. Loading performs
neither provider calls nor code execution, and can inspect evidence from a different runtime.
There is no standalone trusted import, schema migration or reviewed-contract promotion.

Replay requires renewed `allow_untrusted_code_execution=True` **before any I/O**. It verifies the
artifact and refuses unknown identities, original before/after drift or changed current controls
before starting a worker. It then executes the same capture with exactly the saved observation
inventory and execution limits, recomputes comparisons against saved expectations and checks the
new before/after controls again. A changed runtime during replay cannot produce a compatible report.
The returned artifact links to the source artifact's content hash; it never reuses cached outputs
or claims replay duration as model-inference latency. It makes zero model calls.

## Runtime controls and limits

Recorded controls are exact Python version/implementation, platform, machine architecture,
installed metadata versions for `notebook-to-kedro`, `nbformat`, `kedro`, `kedro-datasets`, `numpy`,
`pandas`, `scikit-learn`, `scipy` and `omegaconf`, the supplied project root's `uv.lock` SHA256,
and a deterministic hash of the executing package's Python source tree. Package source hashing
distinguishes editable code changes without requiring Git or importing optional heavy libraries.
Identity-file and cumulative package-source reads are bounded at 16 MiB. Missing optional packages
or lock are recorded as unknown and remain inspectable, but strict replay refuses them.

Before/after sampling detects observed drift, not changes reverted between samples. Metadata
versions and a lock hash do not attest loaded binary/library bytes, all transitive dependencies,
OS/kernel patches, CPU/GPU models, numerical threading or reproducible hardware behavior. The
lock is identified, not proof that the environment was installed with `uv sync --locked`.
No Ollama/model identity is fetched; capture provider/model/prompt metadata remains caller-declared.
Model digest/server controls and reviewed live collection remain later gates.

Hashes provide integrity, **not authentication**. A same-user adversary can rewrite all stored
data or forge worker observations. The subprocess is not an OS sandbox, and raw code/results/logs
may contain sensitive data. Operator-managed isolation, storage permissions and privacy controls
remain required; no cloud loader, tracker or secret handling is added.

Next: genuine human-reviewed contract promotion and durable execution/campaign accounting before
the [whole-notebook live experiment](whole-notebook-experiment.md).
