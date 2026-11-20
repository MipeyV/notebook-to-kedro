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

## Fresh-environment bootstrap

The separate opt-in developer/CI check now includes this committed procedural example under
default and custom profiles, alongside the four existing functional variants:

```bash
uv run python tools/check_generated_bootstrap.py generated/bootstrap-local
```

Each variant builds a wheel and installs its declared `[test]` dependencies in a new venv,
without system packages or the converter. An isolated import probe checks installed-package
location and records resolved distribution versions. Execution uses copied configuration,
data and tests, an empty `src` directory and an empty pytest `pythonpath`; the five shipped
tests and ordinary `python -I -m kedro run` must pass without a source-tree fallback.

The pipeline's final outputs are memory-only. A second real CLI invocation therefore selects
a checker-owned SequentialRunner subclass through Kedro's `--runner` option. It delegates
unchanged to SequentialRunner and observes the resulting datasets after completion. It requires
float64 predictions `[0.0, 1.0, 4.0, 9.0]` and absolute error `0.0`, independent of the shipped
regression declaration. The resulting `observed-cli.json` is checker evidence, not a generated
application artifact or a new persistence contract.

A separate isolated invocation wraps the installed evaluation node in memory, adds one to its
predictions and runs the same CLI observer. It must exit with code 1 **after the runner finishes**
and report exactly `[1.0, 2.0, 5.0, 10.0]` with `observation_mismatch`. Setup/import failures,
unrelated errors, missing reports or an unexpected mutation cannot satisfy this control. No
installed wheel file, source notebook or generated application node is edited.

The check retains logs, JUnit XML, runtime identities and observation/negative-control reports
within each new case directory. `evidence.json` links source, fixture, contract and wheel hashes,
stages, observations and unchanged original regression gaps. Configuration/data hashes are
compared against their pre-test copies, and the original generated project must stay unchanged.
Failures retain evidence and stop the batch; remaining cases are not claimed as executed.

CI runs this same six-variant command on Python 3.11, 3.12 and 3.13 and uploads its evidence even
on failure. Configuring the matrix alone does not establish a passing run. Dependencies resolve
from generated ranges using fresh environments, with downloads potentially cached by uv;
versions identify the specific run rather than a generated lockfile or every supported version.
No real project or provider is executed. Model serialization, positive model/node oracles,
scientific validation and arbitrary notebook support remain outside this check. Generation's
`not_run`/`not_authenticated` report is preserved unchanged.

On 2026-11-20, the first Windows Python 3.12.14 fresh-resolution run passed the four functional
variants, then failed one of five procedural-default tests: Windows application control refused
a scikit-learn 1.9.1 `_radius_neighbors` DLL. The procedural-custom variant did not run. That
failed attempt and its resolved versions remain preserved. A separate run constrained to the
existing development lock's NumPy 2.5.2, SciPy 1.18.0 and scikit-learn 1.9.0 passed all six fresh
installations, using Kedro 1.8.0, pandas 2.3.3 and pytest 9.2.0. Both procedural CLI observations
matched and both mutations were rejected. Generated dependency ranges and system protections
were unchanged; this does not establish unconstrained Windows resolution or every compatible
version. CI checks default resolution independently on Linux.
