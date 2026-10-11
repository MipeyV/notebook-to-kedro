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

## Documentation

The root `README.md` remains the repository and package entry point. The
[documentation index](docs/README.md) provides reading paths and a categorized document list.

- [Product overview](docs/product/overview.md): original scope, goals and design principles.
- [Conversion roadmap](docs/product/roadmap.md): completed V1 milestones and remaining V2 work.
- [Product vision](docs/product/product-vision.md): proposed faithful reproduction,
  industrialization and explicit optimization, including templates, broader catalog inference,
  CV/Bayesian search, segmented KPIs, tracking profiles and MDL-inspired experiments.
- [Architecture](docs/reference/architecture.md): module boundaries and test strategy.
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

## Project name

**Notebook to Kedro** is a working name. The planned Python package name is `notebook_to_kedro`.
