# Compatibility Policy

Structured `.py` input is supported by [`inspect-blocks`](functional-blocks.md) and the separate
[functional workflow conversion](functional-workflows.md), alongside function-based notebooks.
The latter requires an explicit entrypoint and JSON configuration and supports JSON file I/O,
scalar/flat-mapping parameters and bounded single-use calls. Schemas 1.0/1.1 require a linear
data chain; opt-in schema 1.2 also supports independent calls and joins in source order. The conversion support described below
still applies to the original notebook path. Neither entrypoint supports arbitrary Python.

Functional inspection schema 1.1 records explicit terminal return expressions separately from
observed return names. Supported called functions/helpers keep direct calculation or call
returns unchanged in generated projects. The workflow entrypoint still needs named
call assignments and a final named result. Multi-file reconstruction, dependency inference and
typed dataset boundaries remain unsupported. Existing schema 1.0 functional fingerprints change;
local-operation envelopes and project-settings schema versions remain 1.0.

Preserved function bodies also admit structured if/for/while, raises and loop break/continue,
with conservative definite-local-binding checks and one final value return. Original helper ASTs
stay intact. Nested imports/definitions, try/with/match, early/multiple returns, dynamic calls,
comprehensions and mutation writes retain their blockers. Paths, iteration counts and termination
are not proved. This does not enable conditional/iterative orchestration or arbitrary Python.

Workflow configuration schema 1.0 keeps scalar-only parameters. Opt-in schema 1.1 adds flat
string-keyed mappings of finite JSON scalars, with immutable settings and single-use mapping
consumption at the node boundary. Arrays, nested mapping contents, dependency inference and
general DAGs remain unsupported. Generated tests reuse the selected workflow parameter schema.

Workflow schema 1.2 retains the flat mapping and single-use rules while enforcing source call
order using explicit ordering-only dependencies. Business wrapper signatures remain unchanged.
Its plan/manifest uses schema 1.1 ordering metadata; local operations stay schema 1.0. Tests
exercise SequentialRunner, ThreadRunner and adapter pickling, without claiming every process
runner or arbitrary deployment. An optional versioned `shared_data` policy on schemas 1.2 through
1.7 admits only explicitly named intermediate outputs consumed at least twice, with source order
and assign-mode object retention within one process. Catalog inputs, mutable parameters, final/
unused values and undeclared reuse remain rejected. SequentialRunner/ThreadRunner are exercised;
process runners and arbitrary concurrency are unsupported. Plans with this policy use schema 1.7;
local envelopes remain 1.0. Dynamic orchestration and richer typed I/O retain their limits.

Opt-in workflow schema 1.3 preserves one explicitly declared regular Python package containing
the selected `.py` module, including raw resources and original imports. It inherits source-order
and flat-parameter rules. Analysis/plan schema 1.2 includes explicit context/inventory binding;
local envelopes remain 1.0. Supporting modules receive compile-only checks, not functional
reconstruction. Namespace packages, cross-module workflow discovery, inferred third-party
requirements and original distribution metadata remain unsupported. See the
[package contract](functional-workflows.md#explicit-local-package-in-schema-13) for limits,
path rules and the distinction between context-free inspection and package-aware planning.

Separate `prepare-workflow` schema 1.0 previews an explicitly declared call sequence against
observed functions in one regular package. Optional publication creates a new review copy and
forwarding adapter. It shares exact-signature, single-assignment, single-use and final-result
wiring checks, conservatively treating all arguments as single-use. It is not automatic
entrypoint discovery or typed-I/O support. Original conversion guards and local envelopes stay
unchanged. Its synthesized facts and unreviewed status are distinct from original source facts.

Workflow schema 1.4 retains the required regular package and adds explicit raw-file path inputs
with declared sibling sidecars. It hashes/copies bytes under a 256 MiB total limit, supplies
path strings through assign-mode memory datasets and preserves original application readers.
No file format, Parquet execution, domain fingerprint or typed serializer is inferred. Plans use
schema 1.3; analysis/local envelopes remain unchanged. Nested sidecars, remote/external files,
generated file-fixture regression contracts and typed final-result/artifact policies remain
unsupported. JSON-value input/regression behavior remains available independently.

Workflow schema 1.5 additionally permits an explicit `memory` final-output target and retains
existing JSON targets. Assign-mode retention preserves the runtime object/type without inferred
serialization or type validation. SequentialRunner/ThreadRunner and default/custom profiles are
verified on trusted synthetic examples; other process runners and durable recovery are not.
Plans/manifests use schema 1.4, while analysis/local envelopes remain unchanged. JSON regression
contracts do not define typed memory-result comparisons and are rejected for this mode. Durable
result serializers, generated typed comparators and owned application artifacts remain future work.

Workflow schema 1.6 adds explicit artifact destinations tied to flat parameter fields, with up
to eight portable artifacts/<run_name> paths and a bounded generated policy marker. Checks run
at the consuming registered pipeline node; direct function calls bypass them. Source functions
remain unchanged. SequentialRunner/ThreadRunner and callable pickling have trusted fixture
evidence, without a process-runner, sandbox or concurrency-lock guarantee. Legacy modes remain
independent. Plan/manifest schema 1.5 records ownership/check gaps; analysis/local envelopes stay
unchanged. Broad artifact layouts, typed/artifact generated comparators and dependency metadata
are separate work; no real application execution follows from configuration.

Workflow schema 1.7 captures static PEP 621 application declarations from an explicitly selected
pyproject, including requirements, extras, scripts and selected build/provenance resources. It
stages the original project and source layout under `application/` for separate installation,
with an exact application dependency in the generated Kedro distribution. Metadata/file drift and
normalized distribution-name collisions block rendering. Plans/manifests use schema 1.6. The
synthetic wheel/editable-wheel checks reuse locked runtime dependencies and exercise metadata,
resources, shipped regressions and CLI execution. Actual backend installability and fresh
dependency resolution require environment-specific evidence. The contract is documented under
[application distribution](functional-workflows.md#application-distribution-in-schema-17).

Separate preparation schema 1.1 preserves an explicitly selected application project, its
pyproject-relative source layout and selected build/provenance/input files alongside the new
adapter. Preparation manifest schema 1.1 records original and proposed facts with captured
distribution evidence and pending review. Subsequent conversion uses an explicitly configured
workflow schema 1.7. Synthetic src/lib-layout, byte-preservation, collision/drift and installed
standard/editable-wheel checks cover the composition. The
[application preparation contract](functional-workflows.md#application-projects-in-preparation-schema-11)
defines review and installation scope.

Application-aware workflow generation now emits a schema 1.0 published-file inventory. The
separate capture-workflow-provenance API/CLI requires Git at the original source root and a
selected interpreter with the declared original/generated distributions installed. It verifies
listed bytes and source-copy bindings, recomputes prepared lineage and captures installed
metadata in report schema 1.0. Standard/editable synthetic installations are exercised. Original
source, ambient Git, metadata observation and future runtime acceptance retain their own scopes.
The [provenance contract](functional-workflows.md#original-source-and-installed-workflow-provenance)
defines limits and required regeneration for older published projects.

An opt-in [developer paired-trial script](../guides/real-workflow-setup.md#developer-harness)
checks the specific naive/one_step validation artifact contract outside normal engine operations.
Its installed synthetic pairs reuse locked development libraries; PyArrow/editables are test-only
dependencies. After runtime preflight and explicit user review/consent, one private real validation
pair matched its exact scoped expectations and protected postflight checks. Detailed outputs remain
private. This supplies no general executor, scientific quality claim or broader generated regression
compatibility.

The [local operation layer](local-operations.md) configures these same deterministic entrypoints
through typed inspection, new-file preview and generation requests. It adds an explicit contained
working root and local JSON settings, without broadening source/library support or executing code.

The initial [VS Code extension](../guides/vscode-extension.md) targets desktop VS Code 1.145+
and local file workspaces, with host tests pinned to 1.145.3. Its selected interpreter requires
an installed engine with schema 1.0 local operations. Build tooling requires Node 22+ and npm.

[Documentation index](../README.md)

Procedural generated projects can optionally include [standalone regressions](generated-notebook-tests.md)
with supplied pinned CSV fixtures and finite JSON/numeric/array/flat pandas observations.
This notebook-specific contract does not expand functional JSON regression schemas or provide
model/artifact serialization. The five-test synthetic decision-tree example is bounded evidence;
an opt-in [fresh-environment check](generated-notebook-tests.md#fresh-environment-bootstrap)
now exercises the example's wheel, shipped tests and CLI with both profiles, independently
of routine offline verification. Arbitrary notebook support remains separate work.

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

Generated projects declare Hatchling as their build backend and explicitly include their source
package in wheels. The runtime dataset extra is `kedro-datasets[pandas-csvdataset]>=8,<9`,
matching the supported CSV connector; JSON datasets require no additional connector extra.
The scaffold includes `conf/local` for default Kedro CLI startup. A separate
[trusted-example bootstrap check](generated-workflow-tests.md#fresh-environment-bootstrap)
installs the actual wheel without development dependencies or source-path fallbacks.
Its CI matrix targets Python 3.11/3.12/3.13; individual reports record observed versions/results.
Generated dependency ranges are not a lock or proof of every allowed dependency combination.

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
- selected literal pandas preprocessing parameters for `fillna(value=...)`,
  positional `fillna({...})`, and `drop(columns=[...])`.

Complex scopes, conditional writes, dynamic execution, shell commands, and Jupyter magics follow the policy in [mvp-contract.md](mvp-contract.md).

The high-level planning/generation path now applies [source accounting](source-accounting.md).
Standalone expressions/assertions/side-effect cells that the cell-oriented planner cannot place,
unsafe mixed cells, unresolved inputs and non-exact catalog relocation block conversion rather
than disappear silently. A bounded procedural extension accepts mixed cells with leading imports,
at most one exact local CSV load and a source-ordered business data chain. Each instruction has
one import/catalog/task owner; catalog reads cannot disappear or reload across tasks. Imports
interleaved after loading/business, independent steps and retained nested/dynamic CSV readers
are rejected. Current catalog relocation accepts an earlier bound
pandas reader with one positional literal local CSV path and no options. Retaining a loader in
task code is distinct from inferring a catalog entry. These stricter checks do not establish
arbitrary Python equivalence; low-level planners remain proposals and direct generation needs
supplied `source_facts` to check completeness against the source.

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

The first preprocessing pattern supports a single explicit `StandardScaler` object in ordinary top-to-bottom code. Literal `with_mean` and `with_std` arguments are extracted into generated parameters. Selected [nested financial examples](../evaluation/nested-financial-models.md) also preserve authored `ColumnTransformer`, `Pipeline`, voting and calibration source inside ordinary nodes. This supplies composition-specific runtime evidence, not automatic interpretation of arbitrary nested preprocessing graphs. An external fitted-preprocessor alias still exposes a runtime fidelity gap despite complete static accounting.

Pandas preprocessing support currently improves plan naming for direct dataframe rewrites and extracts selected literal `fillna` and `drop(columns=...)` arguments into Kedro parameters. It does not yet infer schemas, validate column existence, parameterize `assign` expressions, or support broad dataframe transformation graphs.

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
    "kedro-datasets[pandas-csvdataset]>=8,<9",
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

The CSV connector is a test-only dependency for real generated-catalog loading. Its 8.x
target matches the existing generator; the locked CSV extra resolves pandas to `2.3.3`
because it requires pandas below 3. The package's core runtime and broader pandas constraint
are unchanged. See the [synthetic pilot](../evaluation/synthetic-notebook-pilot.md) for the
runtime change and why it is not a same-runtime comparison with older model measurements.

## Locking and upgrades

- `uv.lock` is committed.
- CI uses `uv sync --locked`.
- Dependency upgrades are deliberate pull requests.
- Runtime lower and upper bounds live in `pyproject.toml`.
- Exact development and CI resolutions live in `uv.lock`.
- Direct dependencies are not pinned to exact versions in published metadata unless compatibility requires it.
- Generated projects record their own dependency constraints and lockfile independently.

## Compatibility tests

The [synthetic banking/insurance cases](../evaluation/banking-insurance-cases.md) add selected
runtime evidence for ten-cell procedural workflows with temporal partitioning, pandas
imputation/dummy encoding and a seeded forest. Their source-accounting, paired execution and
independent metric checks do not establish generic library semantics, arbitrary notebook
support or fresh-environment installation of those larger workflows. Their two unsupported
layouts remain explicit refusal fixtures.

The separate [nested-model cases](../evaluation/nested-financial-models.md) reuse the same data
and exercise nine-node graphs with fitted-state checks under both profiles/runners. Their
fitted-alias boundary generates but fails at runtime; temporal stacking fails in the source
library and Kedro alike. Static source completeness alone is not behavioral equivalence.

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
