# Local project operations

[Documentation index](../README.md)

Status: first E4 slice implemented on 2026-11-14. Explicit local configuration and typed
inspect/plan/generate operations compose the existing deterministic engine. No local app,
VS Code extension, existing-project patching, provider selection or code execution is included.

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
Functional configuration requires `workflow_configuration`; `regression_contract` is optional.
The notebook kind refuses workflow/regression settings rather than silently ignoring them.
Existing workflow/profile/regression loaders remain authoritative for their separate schemas.
Inspection loads source facts only; planning/generation also load the relevant settings/data.

## Operation behavior

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

## Evidence and next scope

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
retains its explicit trusted-example execution contract. E4 still needs a first interface,
destination/conflict presentation and any approval-bound apply contract selected for that UI.
The independent whole-notebook pilot review remains pending.
