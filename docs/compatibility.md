# Compatibility Policy

## Purpose

Compatibility is defined separately for:

1. the Notebook to Kedro package runtime;
2. Python syntax encountered in notebooks;
3. libraries understood semantically by the analyzer and planner;
4. generated Kedro projects;
5. development and test tooling.

Parsing a library call does not imply semantic support for that library.

## Python versions

The initial package target is:

```toml
requires-python = ">=3.11,<3.14"
```

The CI matrix covers:

- Python 3.11;
- Python 3.12;
- Python 3.13.

Python 3.12 is the primary local development version. Python 3.10 and 3.14 may be evaluated after the deterministic analyzer and Kedro compatibility tests are stable.

The upper bound is an explicit MVP support boundary, not a claim that the package is known to fail on newer Python versions.

## Kedro versions

The initial generated-project target is:

```text
Kedro >=1.5,<2
```

The generator will render one documented Kedro project format at a time. It will not attempt to support legacy Kedro 0.18 or 0.19 templates in the MVP.

Kedro remains a test and backend compatibility dependency until the generator requires runtime imports from it. The deterministic notebook analyzer does not depend on Kedro.

## Notebook format

Initial support:

- Jupyter `nbformat` major version 4;
- Python kernels and Python language metadata;
- physical top-to-bottom cell order;
- code, Markdown, raw, and empty cells.

Execution counters are metadata only. They never reorder cells.

## Python syntax support

Python source is parsed with the standard-library AST of the running interpreter. A notebook using syntax newer than the selected runtime is rejected with a syntax diagnostic.

The first milestone focuses on:

- imports and aliases;
- simple and unpacking assignments;
- functions and classes;
- ordinary calls;
- reads and writes of named values;
- basic cross-cell dependencies.
- selected literal scikit-learn keyword parameters.
- deterministic task naming from Markdown headings and simple ML source patterns.
- simple scikit-learn preprocessing with `StandardScaler.fit_transform(...)` and
  `StandardScaler.transform(...)`.
- simple pandas preprocessing names for dataframe rewrites using `dropna`, `fillna`, and
  `assign`.

Complex scopes, conditional writes, dynamic execution, shell commands, and Jupyter magics follow the policy in [mvp-contract.md](mvp-contract.md).

## Library support levels

### Level 0 — syntactic observation

The AST analyzer can record imports, calls, reads, and writes without importing the referenced package.

Example:

```python
custom_library.transform(df)
```

can be represented syntactically even when `custom_library` is not installed. No semantic guarantee is provided.

### Level 1 — semantic patterns

The planner recognizes selected library operations and can propose meaningful node interfaces.

Initial Level 1 candidates:

| Library | Planned MVP patterns |
| --- | --- |
| pandas | tabular loading, filtering, column selection, missing-value handling, joins |
| NumPy | array creation and common deterministic transformations |
| scikit-learn | splitting, estimator construction, `fit`, `transform`, `predict`, metrics |

Pattern support is introduced operation by operation and documented with fixtures. A library name alone never implies complete support.

Readable node naming is a Level 1 planner feature. It currently recognizes simple scikit-learn workflow patterns and otherwise derives valid identifiers from Markdown headings when present.

The first preprocessing pattern supports a single explicit `StandardScaler` object in ordinary top-to-bottom code. Literal `with_mean` and `with_std` arguments are extracted into generated parameters. This does not imply general support for arbitrary sklearn pipelines, `ColumnTransformer`, or nested preprocessing graphs.

Pandas preprocessing support currently improves plan naming for direct dataframe rewrites. It does not yet infer schemas, validate column existence, or parameterize transformation arguments.

### Level 2 — generated-project integration

The generated Kedro project declares and executes the required dependency correctly.

Initial Level 2 targets:

| Integration | Initial scope |
| --- | --- |
| Kedro | project structure, nodes, pipelines, parameters, registry |
| kedro-datasets | local CSV datasets loaded from literal `pd.read_csv(...)` paths |
| pandas | DataFrame node inputs and outputs |
| scikit-learn | estimator training and prediction |

## Explicitly out of scope for the MVP

The following may be observed syntactically but receive no semantic or generation guarantee:

- PySpark;
- Dask;
- Ray;
- TensorFlow;
- PyTorch;
- XGBoost and LightGBM;
- Polars;
- SQLAlchemy and arbitrary SQL;
- distributed or asynchronous training;
- MLflow tracking;
- cloud-specific datasets;
- deployment, serving, and production monitoring.

Support may be added later through explicit compatibility profiles rather than broad best-effort claims.

## Core package dependencies

The published package starts with the smallest practical runtime surface:

```toml
dependencies = [
    "nbformat>=5.10,<6",
]
```

The standard library provides AST parsing, dataclasses, JSON, hashing, paths, and typing primitives.

The following are not initial core dependencies:

- pandas and scikit-learn, which are fixture dependencies;
- Kedro, which is a generated-project compatibility dependency;
- provider-specific LLM SDKs, which remain optional;
- notebook execution tools, which are test dependencies.

## Dependency groups

Development-only packages are separated by purpose:

```toml
[dependency-groups]
lint = [
    "mypy",
    "pre-commit",
    "ruff",
]
test = [
    "ipykernel",
    "kedro>=1.5,<2",
    "nbclient",
    "pandas",
    "pytest",
    "pytest-cov",
    "scikit-learn",
]
dev = [
    { include-group = "lint" },
    { include-group = "test" },
]
```

Optional features intended for library users belong in `[project.optional-dependencies]`, not development groups.

## Locking and upgrades

- `uv.lock` is committed.
- CI uses `uv sync --locked`.
- Dependency upgrades are deliberate pull requests.
- Runtime lower and upper bounds live in `pyproject.toml`.
- Exact development and CI resolutions live in `uv.lock`.
- Direct dependencies are not pinned to exact versions in published metadata unless compatibility requires it.
- Generated projects record their own dependency constraints and lockfile independently.

## Compatibility tests

Compatibility claims require automated evidence:

- all supported Python versions run the unit and contract suites;
- the primary Python version runs notebook, Kedro, and end-to-end tests;
- generated projects execute against the declared Kedro range or an explicit tested subset;
- library semantic patterns have focused fixtures;
- unsupported cases produce stable diagnostics.

## Adding support

A new library or framework is considered supported only after:

1. the supported operations are documented;
2. representative positive and negative fixtures exist;
3. static and semantic expectations are tested;
4. generated dependency handling is defined;
5. notebook-to-Kedro equivalence is demonstrated where applicable;
6. the compatibility table is updated.
