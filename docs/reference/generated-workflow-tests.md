# Tests delivered with functional projects

[Documentation index](../README.md)

Status: E3 functional regression and bootstrap slices implemented by 2026-11-14. Explicit JSON
expectations produce standalone pytest node/pipeline tests for linear functional workflows.
An opt-in trusted-example check verifies wheel installation and Kedro startup in fresh environments.
Richer comparators and procedural-notebook test generation remain future.

## Generate and run

Workflow schema 1.7 supports the same explicit JSON regression contract after installation of
both the generated project and its staged application. Trusted distribution tests build and
install standard/editable application wheels and generated wheels offline, run supplied node/
pipeline expectations and invoke `python -m kedro run`. They reuse the locked development
runtime's dependencies through an explicit site path. The editable variant verifies a
source-relative project-file hash. Fresh dependency resolution has its own bootstrap scope.
Installation details are in the [distribution contract](functional-workflows.md#application-distribution-in-schema-17).

```bash
uv run notebook-to-kedro generate-workflow examples/functional_workflow/workflow.py examples/functional_workflow/workflow.json generated/tested_workflow --project-root . --regression-contract examples/functional_workflow/regression.json
```

Use the paired `.ipynb` for notebook input. Default/custom profiles work with the same contract.
In Python, load `WorkflowRegressionContract` with `load_workflow_regression_contract` and pass
`regression_contract=contract` to `generate_functional_kedro_project`. Existing workflow
configuration and conversion schemas are unchanged.

After reviewing the generated project and expectations, run from the generated root:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Generation validates data and compiles the emitted test module; it never imports application
dependencies, executes code, measures outputs or infers an expected result. Running pytest
executes project code in the current process: it is not a sandbox. Generated tests need pytest
and the project's runtime dependencies, with no Notebook to Kedro import. `TESTING.md` records
instructions and limits. Generation does not itself perform or certify installation.

## Expectation contract

The committed [example](../../examples/functional_workflow/regression.json) supplies three
hand-specified cases: `abs(-3 * 2) = 6`, `abs(0 * 2) = 0`, `abs(1.25 * 4) = 5`. The first case
also supplies independent intermediate expectations for the two generated wrappers.

```json
{
  "schema_version": "1.0",
  "scenarios": [{
    "id": "negative_value",
    "inputs": {"values": -3.0},
    "parameters": {"scale": 2.0},
    "expected": 6.0,
    "nodes": {
      "step_0000_prepare_values": {
        "inputs": {"values": -3.0, "scale": 2.0},
        "expected": -6.0
      }
    }
  }]
}
```

- Top-level fields are exactly `schema_version` (`1.0`) and `scenarios` (1 to 100 cases).
  Every case requires `id`, `inputs`, `parameters`, `expected`; only `nodes` is optional.
- IDs are unique lowercase identifiers with underscores/hyphens, at most 64 characters.
  Contracts are bounded to 64 KiB UTF-8 and 16 JSON nesting levels. Duplicate keys, non-finite
  values, non-JSON values and unknown/missing fields are rejected.
- Scenario input/parameter names exactly match workflow boundaries. Parameters follow the
  selected workflow schema: finite scalars in 1.0, also flat scalar-valued objects in 1.1/1.2/1.3.
  Input/expected values can be nested finite JSON. The regression contract itself remains
  schema 1.0. Application acceptance is tested only when pytest runs.
- `expected` describes the one final output. `nodes` maps unprefixed step names from
  `plan-workflow` to cases containing exactly `inputs` and `expected`. Node inputs name wrapper
  arguments (source value names), not necessarily the original callee's parameter names.
  Profiles remap wrapper names without changing the expectation contract.
  Schema 1.2 ordering-only inputs are pipeline wiring and are excluded from business node cases;
  the delivered node tests call the unchanged wrappers directly.
- Expectations are operator supplied. Schema validation does not authenticate their review,
  independence or business correctness. They are never automatically filled from execution.

The frozen contract stores canonical JSON rather than mutable trees; exports are fresh copies.
Its SHA-256 identifies supplied data, not correctness or approval.

## Test behavior and gaps

Each scenario creates one pipeline test. The suite loads the real generated catalog, writes
scenario inputs into pytest's temporary directory, injects scenario parameters and runs the
actual registered pipeline. It checks persisted output through the catalog. Original input
bytes, parameter configuration and project output paths remain outside test workspaces.
Generated JSON catalog paths are checked before test I/O; unsupported types and paths outside
the generated layout fail rather than writing elsewhere.

Only supplied node cases create node tests, with copied inputs to avoid cross-test mutation.
Outputs are compared by canonical JSON representation without numeric tolerance. Dictionary
order is ignored; `true`, `1` and `1.0` remain distinct. Python-specific types, approximate
comparisons, error expectations and non-JSON results need later contracts. Application imports
and global state are shared within a pytest process; per-scenario process isolation is not claimed.

`regression-coverage.json` always records scenario counts and missing expectations:

- No contract means no generated pytest suite, passing stub or package test extra.
- Pipeline-only contracts list missing node expectations; missing cases do not become skips
  or automatic successes.
- `execution_status` is `not_run` and `review_status` is `not_authenticated`: this is a
  generation snapshot. Running/editing tests does not update it or its contract hash. Record
  later execution separately using pytest/CI results.

Shipped files are `tests/test_workflow_regressions.py`, `tests/regression_cases.json`,
`TESTING.md` and the gap snapshot. With expectations, the package declares an optional pytest
extra and pytest source/test paths. All validation precedes the existing staging writer.

## Fresh-environment bootstrap

From the repository root, explicitly run the network/install check:

```bash
uv run python tools/check_generated_bootstrap.py generated/bootstrap-local
```

The destination must not exist. This developer tool executes only the committed functional
example, presented as `.py` and `.ipynb`, with default and custom profiles. It is separate from
normal generation and the offline pytest suite; it does not accept arbitrary source paths or
provide a general project execution service. It builds each project's wheel using the declared
Hatchling backend, creates a separate standard-library venv without system packages or pip,
and installs the wheel's `[test]` extra with `uv pip` and fresh dependency resolution.
Downloaded artifacts may come from uv's cache; installed environments are new.

An isolated Python probe checks that the package imports from the venv and that
`notebook_to_kedro` is unavailable, and records actual installed distribution versions.
Tests and `python -m kedro run` then use a copy of the generated configuration, data and tests
with an **empty source directory**. Pytest's `pythonpath` setting is overridden to empty.
Both commands must therefore use the installed wheel rather than the generated source tree.
The check requires all five tests to execute successfully, verifies the persisted CLI result
`6.0`, and checks input/parameter preservation. Execution is trusted fixture code, not a sandbox.

The check keeps build/install/command logs, JUnit XML, runtime identity and per-case
`evidence.json` with source/configuration/expectation/wheel hashes and stage outcomes.
It stops at the first failure; later variants have not run. Failure logs remain available.
It refuses to reuse an existing evidence destination and does not change generation's
`regression-coverage.json` execution/review snapshot.

The separate CI bootstrap job configures Python 3.11/3.12/3.13 on Linux. Its generation environment
installs only locked core dependencies, and reports/logs are uploaded even on failure.
Generated dependencies are resolved from declared ranges, independently of the engine's
development lock; recorded versions identify a run, not a committed generated-project lock.
This checks one synthetic example and selected resolved versions, not arbitrary dependencies,
every version in the supported ranges, production readiness or independent human review.

Generated projects now declare a build backend and explicit source-package inclusion, use the
CSV-specific dataset extra, and include `conf/local` for Kedro's default environment.
The wheel contains application code; configuration, data and tests stay in the generated
project directory and must accompany it when running the project.

## Evidence and remaining E3 work

Workflow schema 1.6 artifact declarations do not yet have a shipped artifact-fixture/comparator
contract. The JSON regression contract is rejected before publication for declared artifacts;
gap snapshots name `missing_artifact_expectations`. Trusted development tests separately check
application-owned bytes, source order, marker/parameter drift, existing targets and partial
failure without cleanup/retry. Those tests do not approve actual user effects or invent business
oracles. A schema 1.6 workflow with no declarations retains the applicable JSON/memory rules.

Workflow schema 1.5 memory outputs do not yet have a typed result-comparison contract. The current
JSON expectation contract is rejected before publication, even when inputs are ordinary JSON.
Without expectations, the gap snapshot records `missing_memory_result_expectations`; no result
coercion or pytest stub is generated. Trusted engine tests separately inspect synthetic domain
result fields, exact reference/type identity, fresh-catalog nonpersistence, application failures
and a JSON-mode serialization negative control. Schema 1.5 JSON mode retains shipped regressions
for supported JSON inputs, checked under default/custom profiles.

Workflow schema 1.4 file references do not yet have a shipped fixture/oracle contract. Supplying
the current JSON regression contract to such a workflow fails before publication. Without one,
the gap snapshot explicitly lists `missing_file_fixtures` and emits no tests. Do not substitute
JSON-decoded values or path literals for real primary/sidecar fixture contents. Engine integration
tests exercise trusted synthetic file loaders and domain errors separately; broader generated
file-fixture tests remain future work. Schema 1.4 with only JSON inputs retains existing regressions.

Trusted preparation tests also convert the separate synthesized adapter after explicitly
supplying JSON I/O and existing pipeline expectations. Both naming profiles pass two emitted
tests; changing the adapter's value/scale binding causes both to fail. This checks a deliberate
integration proposal, not equivalence to a previously absent original orchestration. Preparation
itself emits no test stubs or expectations and retains its unreviewed/not-run snapshot.

The schema 1.3 [package fixture](../../examples/functional_package/regression.json) supplies two
pipeline expectations and no fabricated JSON node cases for its internal dataclass. Missing
node oracles remain in the gap snapshot. Both profiles pass the emitted tests; changing the
copied resource makes both pipeline cases fail. Separate tests build a wheel offline with
development-only Hatchling, run original functions and import the generated pipeline registry from its unpacked contents
after removing generated sources from the import path. This proves package/resource inclusion
and internal type identity, not fresh installation of application dependencies or original
distribution metadata. Normal generation still performs no execution.

Trusted tests execute the shipped suites in fresh Python processes for both source formats
and default/custom profiles. The example produces five passing tests (three pipeline, two node);
a pipeline-only contract produces three, with explicit node gaps. Changing multiplication to
addition causes four failures; changing one expected result causes one. An escaping catalog
path fails before external writes. These controls show active assertions, not general coverage.

Those subprocess tests reuse locked development dependencies; the separate bootstrap check
above verifies installation independently. Local Windows runs passed all four variants on each
of Python 3.11.16, 3.12.14 and 3.13.14: twelve new installed environments, each with five passing
tests and the expected persisted CLI result. These runs resolved Kedro 1.8.0, kedro-datasets
8.1.0, pandas 2.3.3, scikit-learn 1.9.1 and pytest 9.2.0; this differs from the locked development
runtime. Linux CI results are recorded separately by the workflow, not inferred from Windows.
The procedural notebook path and the whole-notebook
pilot's pending human review retain their separate contracts. Richer comparators, dependency
inference/locking and wider fixture coverage remain outstanding.

The separate [developer paired-trial harness](../guides/real-workflow-setup.md#developer-harness)
now compares explicitly declared benchmark-style application artifacts and in-process result
descriptors against a registered generated pipeline. Installed synthetic applications exercise
decoded Parquet/metric comparisons and failure controls. This repository script is not shipped
pytest generation or a runtime operation; the JSON regression contract still rejects unsupported
file-reference, memory-result and artifact expectations. One explicitly user-reviewed/authorized
private real pair matched its scoped expectations; its detailed outputs stay local. That evidence
does not extend the delivered-test contract or approve the independent notebook pilot.
