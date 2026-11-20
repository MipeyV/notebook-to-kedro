# Tests delivered with notebook projects

[Documentation index](../README.md)

The original notebook converter can optionally deliver standalone pytest regressions for
its supported procedural subset. Generation stays static: it reads explicit expectations
and pinned CSV fixtures, binds them to the actual generated graph and compiles test source.
It never executes a notebook to invent an expected result. The independent
[functional regression contract](generated-workflow-tests.md) is unchanged.

## Try the synthetic example

From the repository root:

```bash
uv run notebook-to-kedro generate examples/procedural_regression/workflow.ipynb \
  generated/procedural_regression --package-name regression_example \
  --regression-contract examples/procedural_regression/regression.json
cd generated/procedural_regression
python -m pip install -e '.[test]'
python -m pytest
```

Its three procedural cells prepare four rows, fit a seeded decision tree and compute
in-sample predictions/error. The independent supplied oracle is the four known targets
`[0.0, 1.0, 4.0, 9.0]` with zero absolute error. A header-only fixture exercises the source
assertion. Five shipped tests cover two pipeline scenarios and three node cases. This tiny
in-sample check does not establish generalization or scientific quality.

The [local settings](../../examples/procedural_regression/project.json) select the same contract
for API/CLI/local and VS Code operations. Inspection does not read fixtures; project planning
previews the emitted tests without running them. Bare notebook `plan` remains a conversion
report. Omitting the contract preserves the existing generated project output.

## Explicit contract

`NotebookRegressionContract` and `load_notebook_regression_contract` are public API exports.
Pass `regression_contract=` plus original `source_facts=` to `generate_kedro_project` or the
shared renderer. Source accounting remains mandatory for this opt-in path.

The [example declaration](../../examples/procedural_regression/regression.json) is notebook
schema `1.0`, independent of functional regression schema versions:

- Exact root fields: `schema_version`, `fixtures`, `scenarios`.
- Fixtures map public IDs to exact `path`/`sha256` objects. Paths are portable relative CSV
  files beside the declaration; traversal, duplicate paths, device names and traversed
  links/reparse points are refused. Captures are immutable UTF-8 text preserving raw bytes.
- Zero to 100 scenarios and fixtures; finite JSON, no duplicate keys, at most 16 nested
  levels, 64 KiB manifest, 1 MiB per fixture and 8 MiB total. Every fixture must be used.
- Each scenario has a unique `id`, `inputs`, `parameters` and exactly one `expected` or
  `raises` outcome; `nodes` is optional. Input names exactly match catalog datasets and
  reference fixture IDs. Parameter names exactly match extracted qualified plan names;
  these are test-only overrides, without modifying generated parameters configuration.
- Pipeline `expected` maps a nonempty subset of actual leaf dataset IDs to observations.
  Nodes use original task IDs, such as `task-0000`, with exact wrapper argument inputs and
  all original output names in `expected`. Profiles affect generated callable names only.
- `raises` requires an exact supported built-in `type` and literal `message`; a pipeline
  case also requires the failing task ID as `node`. Supported classes are AssertionError,
  ValueError, TypeError, KeyError, IndexError, RuntimeError and ZeroDivisionError. The message
  is bounded to 4 KiB. Setup errors cannot satisfy a declared business exception.

## Represented values

Descriptors have closed fields; all data must be finite JSON. No Python expressions,
imports, pickle, automatic output capture or model serialization are accepted.

| Kind | Fields after `kind` | Use |
| --- | --- | --- |
| `json` | `value` | Inputs/outputs; canonical JSON comparison distinguishes booleans, integers and floats. |
| `csv` | `fixture` | Node input only; plain pandas CSV loading from the pinned bytes. |
| `number` | `value`, `abs_tol`, `rel_tol` | Output only; finite real scalar, nonnegative explicit absolute/relative tolerances. |
| `array` | `dtype`, `data` | Inputs/outputs; rectangular numeric/boolean lists, exact NumPy dtype and values. |
| `frame` | `columns`, `index`, `index_name`, `column_name`, `dtypes`, `data` | Inputs/outputs; flat unique string columns and row data, explicit index/names/dtypes. |
| `series` | `name`, `index`, `index_name`, `dtype`, `data` | Inputs/outputs; explicit name, index, dtype and values. |

Numeric dtypes are bool, int/uint8/16/32/64 and float16/32/64. Pandas additionally allows
object, string, str, Int64, Float64 and boolean. Materialization may reject data incompatible
with a declared dtype; it happens before any expected-exception context. Observations retain
per-column scalar types rather than coercing mixed numeric frames to one NumPy dtype.
Datetime, missing-value sentinels, MultiIndex, model objects, array scalar shapes and arbitrary
application artifacts need other contracts. Index dtype, pandas attrs and estimator internals
are not observed. This is not a general typed serializer.

## Artifacts and execution boundaries

Generation emits `TESTING.md` and `regression-coverage.json`. A nonempty scenario list also
emits pytest source, a case manifest, hash-named CSV copies and the project's optional
`test` dependency. An empty list emits the gap report without a test stub or pytest extra.
The suite depends on pytest and the generated project's runtime dependencies, without the
converter. No new analysis dependency is added.

Shipped tests verify bounded regular fixture files and their SHA-256 before application
imports. Pipeline setup checks the actual catalog against the plain generated CSV declarations
before constructing datasets. Tests copy selected fixture bytes to ordinal paths under a fresh
pytest temporary directory, so catalog source paths never control test writes. Registered
pipeline execution uses SequentialRunner, Kedro's default memory-copy behavior and explicit
scenario parameters. Expected failures
must escape the declared node as the same exception object, with no final-task outputs.
These checks are not a code sandbox or a guarantee against concurrent filesystem changes.

The report records generation-time `not_run`/`not_authenticated` statuses, source/contract
identities, scenario counts, unobserved leaf outputs, nodes without cases and nodes without
positive expectations. One node's negative case does not supply its positive output oracle.
It is neither measured runtime coverage nor authenticated review. The example deliberately
retains a missing positive model oracle and an uncovered evaluation-node case. Source fidelity
and supplied regression success do not prove the source's business correctness.
