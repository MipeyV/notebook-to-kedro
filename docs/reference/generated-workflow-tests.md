# Tests delivered with functional projects

[Documentation index](../README.md)

Status: initial E3 slice implemented on 2026-11-13. Explicit JSON expectations produce
standalone pytest node/pipeline tests for linear functional workflows. Fresh dependency
installation/bootstrap, richer comparators and procedural-notebook test generation remain future.

## Generate and run

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
instructions and limits. Installation instructions are not verified fresh-installation evidence.

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
- Scenario input/parameter names exactly match workflow boundaries. Parameters remain finite
  scalars; input/expected values can be nested finite JSON. Application acceptance is tested
  only when pytest runs.
- `expected` describes the one final output. `nodes` maps unprefixed step names from
  `plan-workflow` to cases containing exactly `inputs` and `expected`. Node inputs name wrapper
  arguments (source value names), not necessarily the original callee's parameter names.
  Profiles remap wrapper names without changing the expectation contract.
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

## Evidence and remaining E3 work

Trusted tests execute the shipped suites in fresh Python processes for both source formats
and default/custom profiles. The example produces five passing tests (three pipeline, two node);
a pipeline-only contract produces three, with explicit node gaps. Changing multiplication to
addition causes four failures; changing one expected result causes one. An escaping catalog
path fails before external writes. These controls show active assertions, not general coverage.

The subprocesses reuse locked development dependencies. Fresh-environment installation and CI
bootstrap are next. The procedural notebook path and the whole-notebook pilot's pending human
review retain their separate contracts.
