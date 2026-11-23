# Explicit generated notebook validation

[Documentation index](../README.md)

This operation runs supplied tests on a private copy of a generated notebook project. Static
inspect/plan/generate behavior is unchanged. The first slice requires notebook project settings
with a regression contract; functional workflows and arbitrary existing Kedro projects are
outside this execution contract.

## Review, then explicitly run

Generate the project first, then choose an existing Python environment containing its runtime
dependencies and pytest. No packages are installed and no environment is provisioned.

```bash
notebook-to-kedro project validation-plan examples/model_reload/project.json generated/project --python /absolute/path/to/python --output generated/validation-001 --timeout 300
```

Project/output paths resolve inside the configured project root, which in this example is
`examples/model_reload/`. The output must be new and disjoint from the original generated
project, interpreter and source inputs. Review the returned inventory, interpreter, output,
budget and execution notice. The plan reads files and renders existing code without running
the chosen Python, importing application dependencies or creating the attempt directory.

```bash
notebook-to-kedro project validate examples/model_reload/project.json generated/project --python /absolute/path/to/python --output generated/validation-001 --timeout 300 --approved-sha256 <reviewed-plan-sha256>
```

Execution recomputes the plan and refuses stale/missing approval before creating output or
starting a process. The approval identity covers effective settings, selected original input
hashes, expected generated files, the chosen interpreter path/resolved executable hash, output,
timeout and runner source/policy. It is a local explicit execution instruction, not pilot human
review evidence, scientific approval or authorization for a model/provider experiment.

The Python API exports `GeneratedValidationRequest`, `prepare_generated_validation` and
`run_generated_validation` from `notebook_to_kedro`. The latter requires `approved_sha256=` and
accepts a `threading.Event` as `cancel=`. Results are immutable and export detached dictionaries.
The CLI exits zero for review/passing tests, one for refused requests or nonpassing outcomes.

## Captured scope and runtime

The selected project's expected files must match a fresh rendering from its current settings,
source, profiles, type schemas and supplied regression contract. Edited/missing generated files
are refused. Only this renderer inventory is copied; extra project files, environments, cached
bytecode and user-added tests/plugins are not copied or executed. The scope is explicit in
`plan.json`, not a claim that every file in an arbitrary project was captured.

Inventory limits are 4,096 files and 256 MiB of copied bytes. File hashing rejects links/reparse
points within captured paths and enforces read budgets. The explicit Python executable may be
a virtual-environment symlink; its resolved binary is hashed while the chosen venv path is used
for execution. No filesystem/environment lock prevents concurrent changes.

The selected runtime runs the packaged stdlib worker with isolated Python startup. Distribution
metadata records Python/platform/prefix, requested installed package versions and missing
distributions. Dependency version constraints are **not evaluated** and the environment is not
locked/authenticated. Missing distributions stop the worker before importing pytest/project code;
successful metadata lookup alone is not compatibility evidence.

Pytest runs the copied `tests/test_notebook_regressions.py` with the copied `src` path, explicit
configuration/root and a confined conftest search. Plugin autoload and inherited pytest options
are disabled. Output capture is disabled so process output goes to the bounded local log;
Kedro telemetry is disabled. Original tests, source bodies, fixtures, assertions and oracles are
unchanged. Model-reload tests run when supplied; tests may fit models and create artifacts.

The private copy is **not a security sandbox**. Trusted source/dependencies can access the host,
network or external paths. Runtime output files have no disk quota. Original selected input and
project inventories, the copied inventory and interpreter binary are checked after execution;
drift prevents passing status but cannot undo code effects. Site-package contents, arbitrary
extra files and external effects are outside those identity checks.

## Outcomes, cancellation and evidence

The worker budget is an integer from 1 to 600 seconds (default 300). It covers the worker,
including environment inspection and pytest; static review/copying and cleanup are additional.
Cancellation/deadline handling terminates the worker's process group on Unix or attempts
`taskkill /T /F` on Windows, followed by worker cleanup. This is cooperative lifecycle management,
not containment of code that escapes its process tree. A client disconnect/forced termination
can leave a started attempt without terminal evidence; inspect it instead of assuming success.

The desktop client uses `--cancellable-stdin`: a line or EOF requests cancellation without
forcibly killing the supervising engine. CLI Ctrl+C also requests cancellation. Ordinary CLI
execution does not consume stdin for cancellation. Annulled confirmation creates no attempt.

Each exclusive attempt retains:

- `plan.json` and `attempt.json`: approved inventory and started timestamp/identity;
- `project/` and `worker.py`: copied renderer inventory and runner;
- `tests.log`: at most 2 MiB retained, with further output drained and truncation reported;
- `environment.json` and `pytest.xml`, when produced;
- `report.json`: terminal outcome, UTC timestamps, worker/attempt elapsed duration, available
  test counts, process exit code and postflight identity checks.

`duration_ns` covers copying, worker supervision, evidence parsing and postflight, excluding
initial review, recomputed preparation, engine startup and attempt setup. `worker_duration_ns`
records completed supervision separately, including environment checks/tests/cleanup. Neither
is training alone or human effort; do not combine clocks with different scopes into a speedup.

Environment reads are bounded to 64 KiB; JUnit reads to 2 MiB, with DTD/entities refused.
Test counts preserve failures, errors and skips. Zero exit alone cannot pass: positive passing
tests, no failures/errors and unchanged captured identities are required. Outcomes distinguish
`passed`, `failed`, `no_passing_tests`, `environment_missing`, `timed_out`, `canceled`,
`cleanup_incomplete`, `drifted` and `runner_error`. A timeout/cancellation does not certify a
partially written test report. Interrupted attempts retain their started record.

Evidence is local and editable, not an authenticated execution certificate. It establishes only
the supplied tests on the selected snapshot. Missing oracles, modeling limitations and pending
human review remain unchanged. Generation-time `not_run` manifests are never rewritten.

## VS Code

Version 0.4.0 adds **Validate Generated Notebook Project**. Choose the generated folder, existing
runtime Python, worker timeout and a new attempt directory. A read-only review opens before the
explicit **Run tests** confirmation. Cancellation is available during the run. Its outcome/counts,
duration, identity and evidence directory appear in a separate summary group. **Open Generated
Validation Log** displays bounded output read-only, including failed runs. **Open Generated
Validation Report** opens the recorded response as read-only JSON.

Imported financial journey reports remain separate. Selecting different settings/Python or
running another static operation clears the in-memory validation snapshot; saved attempt evidence
remains on disk. Source edits do not refresh snapshots automatically. See [ADR 0031](../decisions/0031-explicit-generated-validation.md).
