# Local project operations

[Documentation index](../README.md)

Status: first E4 slice implemented on 2026-11-14. Explicit local configuration and typed
inspect/plan/generate operations compose the existing deterministic engine. The separate
[VS Code interface](../guides/vscode-extension.md) now exposes these contracts through native controls.

## Configure once, choose an operation

```bash
uv run notebook-to-kedro project inspect examples/local_operations/functional.json
uv run notebook-to-kedro project plan examples/local_operations/functional.json
uv run notebook-to-kedro project generate examples/local_operations/functional.json generated/local_workflow
```

The paired [notebook configuration](../../examples/local_operations/notebook.json) selects the
original procedural notebook engine. The [functional configuration](../../examples/local_operations/functional.json)
selects explicit linear workflows from `.py` or function-based `.ipynb` sources. Selecting a path
does not broaden either engine's supported subset. Existing API/CLI commands remain usable.

```json
{
  "schema_version": "1.0",
  "project_root": "../..",
  "source_kind": "functional",
  "source": "examples/functional_workflow/workflow.py",
  "package_name": "local_workflow",
  "workflow_configuration": "examples/functional_workflow/workflow.json",
  "architecture_profile": "examples/kedro_profiles/team_training.json",
  "regression_contract": "examples/functional_workflow/regression.json"
}
```

This example lives under `examples/local_operations/`; `project_root` is resolved relative
to that configuration file's directory. Source, workflow, profile and expectation paths are
relative to the resulting root and use `/` separators. Absolute/drive-relative file settings,
unknown fields, duplicate keys, invalid kinds/versions and escapes from the resolved root fail.
JSON input is UTF-8 and bounded to 64 KiB. There is no discovery, environment interpolation,
executable configuration, plugin loading or implicit project selection.

Required fields are `schema_version`, `project_root`, `source_kind` and `source`.
`package_name` defaults to `generated_project`; the optional profile retains the existing
limited naming/organization contract. `source_kind` is exactly `notebook` or `functional`.
Functional inspection accepts settings before `workflow_configuration` is defined. Planning
and generation require it and report `LO001` before publication when it is missing.
`regression_contract` is optional. Notebook settings also accept an optional `model_output`
source identifier for [one final persisted model leaf](model-outputs.md). It is not a path or
serializer expression and is rejected for functional sources. Inspection does not bind or load
a model; planning previews the real catalog/declaration files, and generation remains static.
The notebook kind refuses functional workflow settings. Its optional `regression_contract`
uses the separate [notebook regression schema](generated-notebook-tests.md), including pinned
CSV fixtures and supplied typed observations. Inspection does not load that contract;
project planning and generation validate and render it through the shared backend.
Existing workflow/profile/regression loaders remain authoritative for their separate schemas.

Notebook settings additionally accept an optional root-contained `node_types` path to
[explicit dataset type declarations](node-types.md). Inspection still reads source alone;
planning/generation load the bounded file, require its source hash/current dataset bindings,
and preview/publish annotated wrappers plus an unverified declaration report. Functional
settings reject this option. Measurement destinations cannot overlap the declaration file.

Notebook settings may additionally set `enforce_node_types: true`. It requires `node_types`
and prepares generated runtime class checks without executing them. Preview exposes the helper,
decorators and policy report through the same service used by VS Code. False remains omitted
from exported settings and preserves annotation-only/default output. No run/approval token or
automatic change to generation-time validation status is introduced.

The same `node_types` path may select schema 1.1 with bounded DataFrame column/dtype metadata.
No new local envelope/version or execution command is added. Preview/generate validate the
declaration without importing pandas; enforcement later applies at declared runtime boundaries.
Use the credit `project-schema-checked.json` settings for the separately scoped example and
schema-specific regression expectations.

Regression schema 1.1 may reference pinned JSON scenarios relative to its own directory;
planning/generation capture them on each request and expose generated fixture bytes in previews.
See the [fixture contract](generated-workflow-tests.md#scenario-fixtures-in-schema-11) for budgets,
immutable direct-API snapshots and the distinction from runtime file-reference inputs.
Inspection loads source facts only; planning/generation also load the relevant settings/data.

## Operation behavior

The separate [generated validation boundary](generated-project-validation.md) now provides
`project validation-plan` and an explicitly approved `project validate`. They run supplied
notebook tests on a captured copy using a selected existing Python environment, with their own
review/result envelopes. They do not extend `run_local_operation` or change the static operations below.

| Operation | Result | Side effects |
| --- | --- | --- |
| `inspect` | Original notebook facts or functional analysis, with `inspected`/`blocked` status | Read source only; no application imports or execution. |
| `plan` | Recomputed engine plan, complete new text files with UTF-8 SHA-256, and copied-input destinations/hashes | Read source/configuration/input files; create no destination, parent directory or temporary project. |
| `generate` | Published destination and relative file inventory, with `generated` status | Recompute current inputs, then use the shared contained/no-overwrite staging writer. |

Catalog input copies are resolved from the configured root, including relative paths in
procedural notebook plans. Every copy must remain inside that root and refer to a regular
file. This is an explicit working-root contract for these new operations; it does not change
the original procedural generator's handling of relative copy paths. Inputs outside the root
must be relocated and the source/configuration reviewed explicitly.

A generation destination is supplied separately to the request or CLI, relative to the root
or as an absolute contained path. The root itself, escaping paths and existing destinations
are refused. Paths are resolved again when an operation runs, including after settings were
loaded. There is no filesystem lock against concurrent edits or symlink races; the writer's
existing publication and failure limits still apply.

Planning uses the actual compile-only renderers and the writer's read-only file validation.
Functional rendering revalidates wiring against captured source facts before rendering.
Functional schema 1.3 also recaptures the declared source package. Copy previews include data,
original package source/resources and schema 1.4 input bundles with source/target paths and
hashes. Rendered-text previews contain exact proposed text; copy entries do not embed file
contents. Publication
uses those same shared writer contracts. Source-only inspection remains context-free and does
not load the workflow contract to infer relative-import context; package-aware planning requires
the explicit schema 1.3 configuration. Supporting modules are not additional inspected node sources.

Schema 1.5 previews can declare a final memory-only result. The plan/manifest records its mode
and nonpersistence, and catalog text shows assign-mode memory with no filepath. Local operations
still never run a pipeline or transport a domain result in their JSON response. Generation
publishes source/configuration only; source effects and owned runtime artifacts remain separate.

Schema 1.6 previews include `artifact-policy.json`, the generated helper/registered-node adapter
and declared owner/path metadata. Static operations do not check/create a runtime artifact
directory in either source or destination projects. Runtime validation stays `not_run` in the
generation record. Actual application writes, partial files and runtime consent stay separate.
Planning previews new files; it does not diff or patch an existing Kedro project. It is a
review snapshot, not an authenticated approval or a reusable apply token. Generation never
accepts a serialized preview and always recomputes current source/configuration. Valid later
changes produce a new project; invalid drift blocks publication. Callers must review changes
as appropriate; this slice does not enforce binding to a previously approved preview hash.

## Python and result envelopes

```python
from pathlib import Path
from notebook_to_kedro import (
    GenerateRequest,
    InspectRequest,
    PlanRequest,
    load_local_project_configuration,
    run_local_operation,
)

configuration = load_local_project_configuration("examples/local_operations/functional.json")
inspection = run_local_operation(InspectRequest(configuration))
preview = run_local_operation(PlanRequest(configuration))
# Explicit publication, only after reviewing source, settings and preview:
published = run_local_operation(GenerateRequest(configuration, Path("generated/local_workflow")))
```

Configuration, requests and results are frozen dataclasses. Direct API paths use `Path`;
relative destinations use the configured root. A Python settings object is a snapshot: reload
the local settings file explicitly to pick up edits to its values. Referenced source, workflow,
profile and expectation files are read again when the relevant operation runs.
Each result exposes `to_dict()` with envelope
`schema_version: 1.0`, `operation`, `status`, effective `configuration` and
`execution_status: not_run`. Inspection preserves the original fact serializer; planning
preserves the engine plan alongside immutable file/copy previews. Generation additionally
reports `installation_status: not_checked`. Dictionary exports are independent copies.
Python-specific result classes are `InspectionResult`, `PlanningResult` and `GenerationResult`.

The CLI writes one JSON envelope to stdout. Blocked inspection exits 1 while retaining source
diagnostics in JSON; successful operations exit 0. Configuration/operation failures exit 1 with
an error on stderr, preserving the existing CLI error convention. `LocalOperationError` exposes
`code`/`message`: `LO001` identifies configuration/request/path failures; `LO002` wraps expected
engine/I/O failures in `run_local_operation`, retaining their cause and original diagnostic text.
The specific `inspect_project`, `plan_project` and `generate_project` helpers also remain
available; underlying engine/I/O exceptions propagate directly from those helpers.

## Conversion effort measurements

### Opt-in conversion measurements

`measure_local_operation(request, directory, case_id=...)` runs an existing typed operation
and returns its unchanged result. The CLI exposes two optional flags, used together:

```bash
notebook-to-kedro project inspect examples/local_operations/functional.json \
  --case-id functional-example --measurement-dir generated/effort/attempts/01-inspect
notebook-to-kedro project plan examples/local_operations/functional.json \
  --case-id functional-example --measurement-dir generated/effort/attempts/02-plan
notebook-to-kedro project generate examples/local_operations/functional.json generated/effort/project \
  --case-id functional-example --measurement-dir generated/effort/attempts/03-generate
notebook-to-kedro project measurement-summary generated/effort/attempts
```

Default calls collect nothing. Result envelopes and configuration schemas keep their versions.
This adds no VS Code controls, application execution, installation or pipeline validation.
The API is exported from the package root and operations module.

Each attempt directory must be new. The shared writer publishes reservation.json before the
operation; measurement.json is written exclusively afterwards, including errors/interruption.
Reject overlap with source/settings files, enclosing regular packages and the generated target.
Retries need new directories. Missing observations are unfinished with unknown duration;
malformed/unbound evidence is rejected. There is no filesystem lock or automated cleanup.
Relative measurement paths use the caller's CWD, independently of configuration path anchoring.
Explicit sibling paths outside project_root are allowed; the protected-overlap checks still apply.

Schema 1.0 reservations capture case/operation, settings, primary source SHA-256/size,
Python/platform and UTC creation time. Outcomes bind the canonical reservation digest and
record status, monotonic duration_ns, source identity afterwards, finish time and bounded
diagnostics. Exceptions keep their type/diagnostics; blocked inspection keeps its result.
LM002 reports outcome-publication failure after success. During an operation error, the original
exception is retained with a note/warning. Do not blindly repeat generation after publication.

**Timing scope:** only run_local_operation after request construction/configuration loading.
Analysis/rendering/validation/writing inside it are included. Inspect/plan/generate are distinct
requests and may repeat analysis; totals represent recorded operations, not disjoint compiler
phases. Process startup, collection overhead, preparation, installation, runtime validation,
waiting and human work are not automatically timed. Source hashing can warm caches. These
observations do not establish cold-start latency or whole-journey elapsed time.

`summarize_conversion_measurements(directory, effort=None, baseline=None)` reads all direct
attempt directories. Keep declarations/summary files outside that ledger. Empty/mixed-case
ledgers, linked entries, malformed JSON and invalid durations fail with LM001. Known seconds,
statuses and unfinished counts stay separate. A canonical attempts_sha256 binds declarations
to the current observed inventory; new/changed attempts invalidate prior human declarations.
It does not prove the operator included attempts made elsewhere.

### Declared human effort and baselines

Without declarations, human_effort/baseline and savings are null, with comparison.status
not_established. Human active time and elapsed time are not inferred from machine latency or
timestamp gaps. Effort JSON has this shape; fill placeholders and actual observations:

```json
{
  "schema_version": "1.0",
  "case_id": "functional-example",
  "source_sha256": "COPY source_sha256 FROM THE SUMMARY",
  "attempts_sha256": "COPY attempts_sha256 FROM THE SUMMARY",
  "acceptance_criteria": "Same reviewed outputs, expected Kedro layout and passing project checks",
  "setup_mode": "first_use",
  "method": "tool",
  "basis": "estimated",
  "outcome": "in_progress",
  "operator": "actual operator",
  "segments": []
}
```

Segments have exactly activity and seconds. Activities are configuration, adaptation, correction,
review or other. Seconds are finite/nonnegative; booleans fail. At most 1,000 segments and
1 MiB JSON per file are accepted; duplicate/nonfinite values fail. load_effort_declaration loads
strict JSON; summarizing validates semantics. Optional elapsed_seconds records journey time
independently. Basis is measured/estimated; outcome is accepted/in_progress/blocked/abandoned.
Set accepted only after reviewing criteria, independently of generation success. Setup mode
first_use/reuse is explicitly declared rather than inferred from installed dependencies.

A baseline uses the same schema/case/source/criteria/setup values, method manual or
general_assistant and its own operator/basis/outcome/segments/optional elapsed_seconds.
It does not need attempts_sha256. Both declarations live outside the attempts directory:

```bash
notebook-to-kedro project measurement-summary generated/effort/attempts \
  --effort generated/effort/human.json --baseline generated/effort/baseline.json
```

Comparison requires matching declarations, stable common primary source, effort bound to the
inventory, no unfinished attempts and accepted outcomes for both methods. Failed/interrupted/
blocked attempts remain in the inventory/totals. Different task/source/criteria/setup declarations
are rejected; changed/unavailable source leaves savings unestablished. Source binding covers the
primary file, not all datasets, resources, dependencies or business intent. Input equivalence and
acceptance remain operator declarations.

Eligible human savings equal baseline active seconds minus assisted active seconds. Elapsed
savings are separate, computed only when both supply them. Never add human/machine durations
to invent elapsed time. Negative savings remain; zero baseline gives no percentage. Status is
operator_declared_measurement when both bases are measured, otherwise operator_declared_estimate.
Neither authenticates a reviewer, proves causality, grants execution consent or accepts the
notebook pilot. Local reports can contain paths, identities and names; there is no automatic upload.

Product evaluation compares the same accepted task across normal manual work, a general coding
assistant and this tool. Include configuration/corrections/review and failures, separating first
use from reuse. Engine development investment and pipeline execution differ from per-project
conversion effort. The earlier private paired trial establishes scoped behavior; engineering
time was not measured and no gain is retroactively assigned.
[ADR 0019](../decisions/0019-opt-in-conversion-measurements.md) records these boundaries.

## Evidence and next scope

### Preparing a prospective comparison

Once a case has complete operation records, a stable common primary source and at least one
successful generation, prepare consistently bound draft forms:

```bash
notebook-to-kedro project prepare-effort-comparison generated/effort/attempts \
  generated/effort/comparison \
  --acceptance-criteria "Same supplied inputs, target conventions and reviewed conversion checks" \
  --setup-mode reuse --operator "pending human operator"
```

The API is `prepare_effort_comparison(directory, output, acceptance_criteria=..., setup_mode=...,
operator=...)`, exported from the root/operations modules. Output must be a new direct sibling
of the ledger. This keeps forms outside the attempt inventory and limits publication placement;
the shared writer refuses existing targets and prepares all files privately before publication.

The five outputs are tool-effort.json, manual-baseline.json, assistant-baseline.json,
measurement-summary.json and README.md. The summary freezes current machine observations.
All forms share case/source/criteria/setup fields. Only the tool form binds attempts_sha256;
the others select manual/general_assistant methods. Every form starts estimated/in_progress
with empty segments. These are collection drafts, not observed zero human time, accepted
projects or execution approval. Field validation and an inventory recheck precede publication.

Keep configuration, adaptation, correction and review effort in scope for each method. Record
human intervals and elapsed time prospectively rather than reconstructing them from machine
durations. If a tool solution has already been seen, use an independent operator or fresh,
counterbalanced matched tasks to reduce learning bias. Source bytes and labels are partial
evidence; verify data, dependencies, requirements and actual task equivalence separately.
This function neither copies/freezes a workspace nor validates business behavior.

New/changed attempts invalidate the tool form. Prepare a new sibling output, preserve earlier
records and explicitly carry actual human observations forward. Review the same acceptance
criteria for each method before declaring accepted. Estimated or incomplete baselines keep
their labels; drafting the forms does not establish productivity gains or approve the notebook
pilot. Application execution retains its separate consent contract.

A local collection pilot now has two committed controlled cases and one real private application
starting from an already prepared workflow. Static inspect/plan/generate completed for each;
all three kits are pending human collection. The real case excludes its earlier adapter creation,
installation and runtime validation. This is preparation of differing scoped tasks, not a
representative corpus or a measured productivity comparison. Detailed records remain ignored
locally; protected files from the earlier private runtime trial were rechecked unchanged.

### One-prompt agent check

On 2026-11-17, a user-requested external coding-agent experiment used fresh context, one fixed
detailed prompt and the same prepared synthetic functional script/configuration/profile/oracles
as the converter. The agent received no corrective coordinator follow-up or converter solution.
It could use only the generic shared writer to publish its authored files, never transformation
or test-rendering APIs. This is separate from engine providers; no transport was implemented.

Both projects passed independent checks against actual catalogs/registered pipelines: two connected
prefixed nodes, preserved helper ASTs, JSON input/output, assign-mode memory intermediate, explicit
parameters, three pipeline and six node expectations, standard Kedro CLI execution and delivered
tests. Their tests rejected two arithmetic source mutations in separate copies. Canonical candidate
inventories and all six shared input files were rechecked unchanged.

| Observation | Coding agent | Deterministic converter |
| --- | --- | --- |
| Delivered tests passing independently | 11 (nine supplied expectations plus two AST checks) | 9 |
| Production phase observation | Approximately 319 s dispatch-to-completion clock window | 0.356 s in-process setup/imports and inspect/plan/generate |
| Successful common independent acceptance | 8.710 s | 8.488 s |
| Retained unsuccessful verification | Metadata probe, Windows temp-directory errors, obsolete DataCatalog.add test-harness call corrected internally | First coordinator check hit Windows temp-directory access errors (4.556 s); common harness corrected |

The agent window includes reading, authoring, internal corrections, its tests, CLI checks and a
voluntary offline wheel build, plus coordinator/tool scheduling at one-second clock resolution.
Converter timing begins with already supplied configuration and excludes prior source/specification
preparation, process startup, human review and the separately reported acceptance. The agent's wheel
build is additional evidence; common acceptance did not build/install either project. No speedup
ratio is inferred from these different boundaries. Exact agent model identifier, tokens and cost
were not exposed; human preparation/correction/review intervals remain uncollected.

The initial coordinator failure is preserved. Both candidates then used the same corrected checker
with new contained pytest temporary directories; neither canonical candidate was repaired by the
coordinator. The agent also retained its own failed attempts. Detailed prompt, inventories, candidate
projects and logs remain ignored locally. The original manual-first input case remains unchanged.
This one tiny functional script and ready environment establish a scoped successful example,
not notebook accuracy, fresh-environment installation, independent human acceptance or productivity.
No real financial workflow/data was exercised and broader pilot review retains its own scope.

A later [three-case expansion](../experiments/prepared-agent-comparison.md) now exercises an
explicit-function ML notebook, ordered join and original package/resource. Both methods passed
common independent acceptance; the public synthetic corpus and aggregate observations preserve
the prepared starting state, separate production/acceptance clocks, corrections and limitations.
This adds evidence rather than a new measurement or provider API.

The subsequent [boundary-focused extension](../experiments/prepared-agent-comparison.md#boundary-focused-extension)
retains blocked inspect/plan/generate attempts for oversized regression contracts, helper control
flow and shared mutable fan-out. Agents met the same frozen task intent in separate projects, but
the engine published no project for these inputs. Refusal durations must not be presented as accepted
conversion latency. Inspection success alone does not establish generation eligibility.

The separate `prepare-workflow` API/CLI operation previews declared orchestration before I/O
configuration and optionally publishes a new review copy. It is not an additional schema 1.0
local operation or VS Code command. Existing inspect/plan/generate behavior remains unchanged;
once an adapter and supported I/O are supplied, ordinary workflow conversion can use its actual
saved source. See the [preparation contract](functional-workflows.md#explicit-orchestration-preparation).

Tests compare previews and published files byte-for-byte with both existing generators,
including functional script/notebook inputs, copied CSV/JSON data and supplied regressions.
They check root anchoring from another CWD, strict configuration, unchanged files during
preview, changed source rejection, resolved path drift, external inputs and no-overwrite behavior.
An unavailable application import still permits static generation. The extracted renderer
rejects a tampered workflow plan. Subprocess integration tests execute all five shipped
regressions for both functional source formats with a configured custom profile, without
changing the original generation snapshot's execution status.

These are bounded deterministic fixtures, not arbitrary-project or runtime equivalence claims.
Both source kinds also pass preview checks in core-only Python 3.11/3.13 environments with
Kedro and pytest absent. The built engine wheel includes the operation modules and retains
nbformat as its only runtime dependency.
Normal operations never run pytest, install dependencies, invoke Kedro, execute source or
contact a model. The separate [bootstrap check](generated-workflow-tests.md#fresh-environment-bootstrap)
retains its explicit trusted-example execution contract. E4 now has an initial VS Code interface.
Setup simplification and any approval-bound apply contract remain further work.
The independent whole-notebook pilot review remains pending.

Functional workflow schema 1.7 flows through the same local plan/generate operations. Copy
previews include the staged application pyproject, selected project files and original source
layout, with exact byte hashes. The manifest exposes captured static distribution declarations
and `not_run` build/resolution statuses. Generated setup instructions describe installing both
local projects. The actual VS Code host test exercises inspection and preview for this schema.
