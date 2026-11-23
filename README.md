# Notebook to Kedro

> Progressively transform a reasonably clean Data Science notebook into a structured, reproducible Kedro project that is easy to review.

## Project status

The deterministic V1 path is operational for a controlled notebook subset: static analysis,
reviewable planning, reports and minimal Kedro project generation. Supported patterns include
simple local CSV catalog inputs and selected pandas/scikit-learn transformations and parameters.

Optional local Ollama planning can propose constrained naming/grouping changes. Node-code
proposals have separate validation and consent-gated benchmark/replay tools; accepted model
proposals are not automatically written into generated projects. Small synthetic measurements
do not establish arbitrary-notebook accuracy. A [draft whole-notebook pilot](docs/evaluation/synthetic-notebook-pilot.md)
now checks a seeded simulation plus real CSV catalog loading against explicit expectations.
Independent human review is still required before a whole-notebook model experiment.

See the [compatibility policy](docs/reference/compatibility.md) for support boundaries and the
[detailed status](docs/product/project-status.md) for APIs, measurements and limitations.
The tool does not promise automatic production deployment or support for arbitrary Spark/cloud
workflows. It preserves source provenance and reports unsupported or ambiguous behavior.

An optional [model output declaration](docs/reference/model-outputs.md) saves one selected
notebook leaf through versioned local storage. Explicit
[prediction probes](docs/reference/generated-notebook-tests.md#explicit-persisted-model-prediction-checks)
can generate standalone tests that reload its saved version in a fresh process. Generation
remains static and expected predictions must be supplied.

## Installation

Notebook to Kedro requires Python 3.11, 3.12, or 3.13. Until the package is published to PyPI,
install the wheel attached to a GitHub Release:

```bash
python -m pip install notebook_to_kedro-0.1.0-py3-none-any.whl
```

For development from a source checkout:

```bash
uv sync --locked
uv run notebook-to-kedro --help
```

## Quick start

Review the deterministic conversion plan before generating files:

```bash
notebook-to-kedro plan notebooks/model.ipynb > conversion-report.md
```

Generate the Kedro project into a new destination directory:

```bash
notebook-to-kedro generate \
  notebooks/model.ipynb \
  generated/model_project \
  --package-name model_project
```

Generation refuses to overwrite an existing destination. Review the generated project and report,
install the generated project's dependencies, then use `kedro run` from its root.
Both the API and CLI enforce plan validation. Rendered Python is compiled without execution,
and files/data are prepared privately before publication. These structural checks do not establish
behavioral equivalence or installation success. A separate
[trusted-example bootstrap check](docs/reference/generated-workflow-tests.md#fresh-environment-bootstrap)
builds and installs fixed functional/procedural example wheels in fresh environments and checks
tests plus `kedro run`.
High-level notebook planning also performs [source accounting](docs/reference/source-accounting.md):
omitted or duplicated statements, changed task/import evidence and unsupported CSV relocation
block generation. Unsupported standalone assertions/side-effect cells are reported for review.

Generated node wrappers include Google-style docstrings and provisional type annotations.
Unknown runtime types remain explicit `Any`; scalar parameter hints describe configured defaults.
Source assertions stay intact and their optimization-mode limitation is documented. See the
[generated interface boundary](docs/reference/source-accounting.md#generated-node-documentation-and-annotations).

An optional [dataset type declaration](docs/reference/node-types.md) supplies reviewed scalar,
pandas/NumPy and sklearn interface types instead of `Any`. It binds to the notebook hash and
actual dataset versions, preserves source bodies and reports missing types separately from
runtime validation. Preview the credit example with `project plan` and
`examples/nested_financial/credit_pipeline/project-typed.json`.

To prepare runtime class checks, select `project-checked.json` in the same directory or use
`--enforce-node-types` with `--node-types` when generating. Checks raise explicit `TypeError`
before source execution for incompatible inputs and before returning incompatible outputs to
Kedro. Schema 1.1 can additionally enforce declared DataFrame columns and dtype labels.
Generation still executes no notebook; row values/fitted state and source assertion repair
remain outside these checks. See the
[runtime boundary](docs/reference/node-types.md#optional-runtime-class-enforcement).

VS Code 0.3.2 displays these type/schema declarations, coverage gaps and prepared runtime
tasks in its read-only conversion summary after Preview or Generate. Validation remains
separate; select `project-schema-checked.json` in the credit example to review both schemas.

Apply a reusable [Kedro architecture profile](docs/guides/kedro-profiles.md) explicitly with
`--architecture-profile examples/kedro_profiles/team_training.json` on both `plan` and `generate`.
This initial schema configures the single pipeline's name and a function/node prefix, with
reviewable source mappings and a generated profile manifest. Omitting it preserves today's output.

Deterministic planning remains the default. After installing Ollama and downloading a local model,
opt into hybrid semantic planning explicitly:

```bash
notebook-to-kedro plan notebooks/model.ipynb \
  --planner hybrid \
  --ollama-model your-local-model
```

The same planner options are accepted by `generate`. Hybrid planning uses only the loopback Ollama
server; invalid responses, connection failures, and unsafe suggestions fall back to the reviewed
deterministic plan and are identified in its diagnostics. When static constraints permit no task
merges, hybrid mode returns the deterministic plan without contacting Ollama.

### Notebooks without user-defined functions

The [banking/insurance corpus](examples/banking_insurance/README.md) supplies 4,200 synthetic
credit records and 5,040 synthetic policy records, with ten-cell procedural notebooks, temporal
validation, explicit tests and preserved unsupported layouts. See the
[measured conversion evidence](docs/evaluation/banking-insurance-cases.md) and modeling limits.

The [nested-model extension](examples/nested_financial/README.md) reuses the same records with
ColumnTransformer/Pipeline preprocessing and a temporally calibrated voting ensemble. Its
nine-node cases retain original failure evidence. The fitted-alias layout is now blocked by
[SA009](docs/reference/source-accounting.md#fitted-pipeline-aliases); temporal stacking retains
its original source library error.

An opt-in [financial journey](docs/evaluation/nested-financial-models.md#measured-installation-journeys)
now runs both nested models/profiles through measured configuration/preview/generation, fresh
wheel installation, delivered tests and exact-version reload. It captures original-source
validation references explicitly and retains human effort as unmeasured:

```bash
uv run python tools/check_financial_journey.py generated/financial-journey
```

An optional [model output declaration](docs/reference/model-outputs.md) now saves one final
notebook output through the Kedro catalog. Use `--model-output fitted_model` or the examples
`project-model.json` settings. Default generation stays memory-only; reload evidence is separate
from the supplied calculation regressions.

Optional [delivered notebook tests](docs/reference/generated-notebook-tests.md) use supplied
expectations and SHA-pinned CSV fixtures via `generate --regression-contract`. The
[three-node example](examples/procedural_regression/workflow.ipynb) ships five standalone
pytest checks and reports missing positive node oracles. Generation does not execute them.

The original notebook path accepts procedural code; functions are not required. The
[mixed-cell example](examples/procedural_notebook/workflow.ipynb) combines imports, CSV loading
and preparation in its first code cell, followed by ordinary split, training and evaluation
cells. It generates four nodes, a CSV catalog and five extracted parameters:

```bash
uv run notebook-to-kedro plan examples/procedural_notebook/workflow.ipynb
uv run notebook-to-kedro generate examples/procedural_notebook/workflow.ipynb generated/procedural_project
```

The existing local/VS Code operations can select
[its settings](examples/procedural_notebook/project.json). This initial mixed-cell scope requires
leading imports, at most one supported CSV load and a data chain preserving source order.
Unsafe cells remain blocking diagnostics; source is never silently omitted. See
[source accounting](docs/reference/source-accounting.md#procedural-mixed-cells) for limits.
Notebook tests use their own [explicit fixture contract](docs/reference/generated-notebook-tests.md),
independently of functional workflow regression schemas.

## Documentation

Inspect explicit functions in a structured script or notebook without executing code:

```bash
notebook-to-kedro inspect-blocks examples/functional_blocks/workflow.py
```

The [functional inspection contract](docs/reference/functional-blocks.md) describes interfaces,
function dependencies, retained source/provenance and blockers. This first E2 slice is analysis
only. The separate [functional workflow conversion](docs/reference/functional-workflows.md)
now generates Kedro projects from explicitly configured entrypoints in either format:

```bash
notebook-to-kedro generate-workflow examples/functional_workflow/workflow.py examples/functional_workflow/workflow.json generated/functional_project --project-root .
```

This initial subset uses JSON file boundaries and explicit scalar or flat candidate parameters.
The [real-workflow setup guide](docs/guides/real-workflow-setup.md) distinguishes the working
candidate, ordered-join and explicit package slices from remaining typed-I/O and artifact gaps. Internal helper calls
remain inside their owning node, including direct expression returns. Entrypoints keep explicit
named calls: schemas 1.0/1.1 require a linear data chain, while opt-in schema 1.2 preserves source
order across independent calls and joins. Schema 1.3 additionally preserves one explicitly declared
local Python package and its resources under its original import name; it does not infer external
dependencies or reconstruct project metadata. Original helper bodies retain supported control flow.
An explicit [shared-data policy](docs/reference/functional-workflows.md#shared-intermediate-references-policy-10)
can share named intermediate objects while preserving source order within one process. Dynamic
orchestration and sharing catalog inputs or mutable parameters remain unsupported. Supply
`--regression-contract examples/functional_workflow/regression.json` to also deliver
[pytest node/pipeline regressions](docs/reference/generated-workflow-tests.md) based on explicit
expected values. Missing expectations are reported; generation never executes code to infer them.

Schema 1.4 adds [raw file references with declared sibling sidecars](docs/reference/functional-workflows.md#raw-file-path-inputs-in-schema-14).
The engine copies and hashes their bytes, then passes a path to the original application loader.
It does not infer data formats or serialize typed results. Shipped JSON regression contracts do
not yet define file-reference fixtures; those gaps remain explicit.

Schema 1.5 can explicitly retain a final Python object with `"outputs": {"result": "memory"}`.
It preserves the original object in the execution catalog without JSON coercion or disk
persistence. See the [memory-result boundary](docs/reference/functional-workflows.md#memory-only-final-results-in-schema-15)
for lifetime limits and missing typed-result expectations.

Schema 1.6 adds [declared runtime artifact destinations](docs/reference/functional-workflows.md#declared-runtime-artifact-destinations-in-schema-16),
bound to exact flat-parameter fields such as `candidate.output`. The registered pipeline checks
the new destination before its owning call; original application code owns creation, writes and
partial failures. Generation creates no runtime artifact directory.

Schema 1.7 captures explicitly selected application metadata, dependencies, extras and project
files. It stages the original installable project under `application/` and links its distribution
identity from the generated Kedro project. The generated README describes installation of both
local projects. See the [distribution contract](docs/reference/functional-workflows.md#application-distribution-in-schema-17).

When a package exposes functions without an entrypoint, use the separate
[orchestration preparation](docs/reference/functional-workflows.md#explicit-orchestration-preparation)
operation: `prepare-workflow SOURCE DEFINITION` previews explicitly declared calls;
`--output-dir NEW_DIRECTORY` publishes a review copy with a new forwarding module. Original
source facts stay separate from the synthesized proposal. Persistent I/O and artifact policies
still need explicit contracts before complete conversion.

Preparation schema 1.1 also preserves a selected original application pyproject and project files,
with the adapter in the original package layout. This review copy can feed the schema 1.7
converter with explicit I/O settings. See the
[application preparation contract](docs/reference/functional-workflows.md#application-projects-in-preparation-schema-11).

Use `capture-workflow-provenance` after application-aware generation and installation to bind
the original source Git commit, published file hashes and selected interpreter's installed
versions in a new report. The source and execution-directory Git contexts have explicit fields.
See the [workflow provenance contract](docs/reference/functional-workflows.md#original-source-and-installed-workflow-provenance).

Use an explicit [local project configuration](docs/reference/local-operations.md) to select the
existing notebook or functional engine and reuse settings across operations:

```bash
notebook-to-kedro project inspect examples/local_operations/functional.json
notebook-to-kedro project plan examples/local_operations/functional.json
notebook-to-kedro project generate examples/local_operations/functional.json generated/local_workflow
```

`plan` previews all new files without writing them; `generate` recomputes current inputs and
publishes a new contained destination. Python callers use the same typed requests/results.
These operations do not execute project code, install dependencies or contact a model.

Opt into [conversion effort measurements](docs/reference/local-operations.md#opt-in-conversion-measurements)
with `--case-id` and a new `--measurement-dir`. `project measurement-summary` reports operation
times and retained attempts. Human effort and manual baselines are explicit declarations;
pipeline execution time alone does not establish conversion time saved.

`project prepare-effort-comparison` prepares pending tool/manual/general-assistant forms with
shared task criteria and the current measurement inventory, ready for prospective human collection.

The initial [VS Code extension](docs/guides/vscode-extension.md) exposes these operations from
Explorer with guided configuration creation, interpreter selection, diagnostics, read-only previews and confirmed
generation. Build its installable VSIX with `npm ci` and `npm run package` in `extensions/vscode`.

Version 0.3.0 adds a read-only conversion/validation summary with supplied-test gaps and session
process timings. Explicit financial journey report imports display separate reported outcomes;
they do not verify the current configuration or measure human savings.

The root `README.md` remains the repository and package entry point. The
[documentation index](docs/README.md) provides reading paths and a categorized document list.

- [Product overview](docs/product/overview.md): original scope, goals and design principles.
- [Conversion roadmap](docs/product/roadmap.md): completed V1 milestones and remaining V2 work.
- [Product vision](docs/product/product-vision.md): ML engineering automation through existing-project
  transformation and future greenfield generation, with reusable enterprise standards.
  Initial naming/organization profiles are available; broader standards, integrations and
  explicit optimization remain proposed capabilities.
- [Architecture](docs/reference/architecture.md): module boundaries and test strategy.
- [Source accounting](docs/reference/source-accounting.md): inspect statement destinations and
  the initial source-fidelity/graph guard reused by notebook conversion.
- [Evaluation and experiments](docs/README.md#evaluation): protocols, corpora and measured evidence.

Product objectives are not supported-feature claims. Optimization requires a separate approved
contract and must not weaken faithful-conversion guarantees. Decisions about future applications
or separate repositories are recorded in the product vision; the shared core stays here for now.

## Contributing

The project uses [uv](https://docs.astral.sh/uv/) for Python and dependency management.

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run pre-commit install
```

The committed `uv.lock` file defines the reproducible development and CI environment. See [docs/decisions/0001-use-uv.md](docs/decisions/0001-use-uv.md) for the decision record.

Release history is recorded in [CHANGELOG.md](CHANGELOG.md). Maintainers should follow the
[release process](docs/guides/releasing.md) when preparing tags and GitHub artifacts.
Development history remains in [JOURNAL.md](JOURNAL.md). See the documentation index's
[maintenance rules](docs/README.md#maintaining-documentation) when adding or moving documents.
Repository agents should follow [AGENTS.md](AGENTS.md).

## Project name

**Notebook to Kedro** is a working name. The planned Python package name is `notebook_to_kedro`.
