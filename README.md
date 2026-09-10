# Notebook to Kedro

> Progressively transform a reasonably clean Data Science notebook into a structured, reproducible Kedro project that is easy to review.

## Context

Machine Learning workflows often begin in a Jupyter notebook used as an experimentation environment:

```text
data loading
    → preprocessing
    → feature engineering
    → train/test split
    → training
    → prediction
    → evaluation
```

When an experiment needs to become a maintainable project, much of the work consists of manually restructuring the notebook:

- extracting functions;
- identifying the inputs and outputs of each step;
- building Kedro nodes and a pipeline;
- moving parameters into configuration;
- declaring datasets;
- organizing the code and separating responsibilities;
- making the workflow reproducible and testable.

This work is valuable but repetitive. **Notebook to Kedro** aims to automate its mechanical parts while exposing ambiguities that require human judgement.

## Goal

The target library interface is deliberately simple:

```python
from notebook_to_kedro import convert

report = convert(
    input_path="notebooks/model.ipynb",
    output_path="generated/my_kedro_project",
)
```

Eventually, the generated directory should be a coherent Kedro project whose workflow can be started with:

```bash
cd generated/my_kedro_project
kedro run
```

Success means more than generating syntactically valid code: the observable outputs of the generated project should be comparable to those of the source notebook.

## Positioning

This project does not promise to turn any chaotic notebook into production-ready code automatically.

Instead, it aims to:

> automate much of the repetitive refactoring required to turn a reasonably clean, sequential ML notebook into a structured Kedro pipeline, with explicit diagnostics and human review.

The tool should distinguish between three outcomes:

1. conversion is supported;
2. conversion is possible but produces warnings;
3. conversion is rejected with an actionable explanation.

## Initial scope

The MVP will target notebooks that are:

- written in Python;
- syntactically valid;
- executable in cell order;
- independent of previous interactive state;
- primarily using named variables to pass results between steps;
- composed of reasonably explicit data transformations and ML steps.

The MVP will not attempt to support:

- cells executed in an inconsistent order;
- Jupyter magics and shell commands;
- `exec`, `eval`, or dynamic imports;
- mutations and side effects that cannot be determined statically;
- complex external dependencies or the inference of their exact versions;
- every Machine Learning framework;
- deployment, serving, production monitoring, or cloud infrastructure.

When a construct is not supported, the tool should report it rather than silently generate a questionable result.

## Proposed architecture

```text
Notebook .ipynb
      ↓
Loading and validation
      ↓
Cell-level AST analysis
      ↓
Symbol and dependency resolution
      ↓
Intermediate representation + diagnostics
      ↓
Versioned Kedro generator
      ↓
Transactional filesystem writer
      ↓
Generated project + conversion report
```

### Loader

The loader opens the notebook, validates its format, and returns its cells in source order. It performs no semantic analysis.

### Analyzer

The analyzer relies on Python's AST wherever possible to identify:

- imports;
- defined and referenced symbols;
- functions and classes;
- dependencies between cells;
- suspicious mutations or side effects;
- unsupported constructs.

Static analysis alone cannot guarantee semantic equivalence, so its limitations must be represented in the diagnostics.

### Intermediate representation

Notebook analysis will not generate Kedro code directly. An intermediate representation will describe tasks, their inputs and outputs, their provenance, and recognized parameters.

Conceptual example:

```python
Task(
    name="train_model",
    source_cells=(5,),
    inputs=("X_train", "y_train"),
    outputs=("model",),
    parameters=("learning_rate",),
    source_code="...",
)
```

This boundary will allow analysis and generation to evolve independently.

### Kedro generator

The generator will consume only the intermediate representation. It will create a Kedro structure compatible with an explicitly targeted version, including:

- node functions;
- the pipeline definition;
- pipeline registration;
- parameter configuration;
- a catalog for persistent inputs and outputs;
- the minimum project files required for execution.

## Design principles

- **Determinism first**: parsing, dependency analysis, generation, and validation do not depend on an LLM.
- **Traceability**: every generated task remains linked to its source cells.
- **Explicit failure**: significant ambiguity blocks conversion or produces a visible warning.
- **No silent overwrites**: an existing destination is protected by default.
- **Simplicity**: focused functions, dataclasses, and modules before broader abstractions.
- **Testability**: analysis decisions and generated projects can be tested independently.
- **Human review**: the conversion report is part of the product.

## Possible future role for an LLM

The core MVP will remain deterministic. A later version could use an LLM to assist with:

- domain-aware node naming;
- block classification;
- grouping multiple cells;
- extracting ambiguous parameters;
- refactoring complex imperative code;
- suggesting tests.

Such suggestions would still pass through deterministic validation and be presented to the user before adoption.

## Project status

The project is currently implementing its deterministic analysis frontend. No converter has been implemented yet.

The first technical milestone is a notebook analyzer that produces an inspectable intermediate representation without generating a Kedro project.

The initial deterministic analysis contract is documented in [docs/mvp-contract.md](docs/mvp-contract.md), and its interchange model is defined in [docs/notebook-facts-schema.md](docs/notebook-facts-schema.md).

The first reference fixture runs a deterministic Iris classification workflow. It provides a known-good baseline whose predictions and accuracy can later be compared with the generated Kedro pipeline.

The planned module boundaries and test strategy are described in [docs/architecture.md](docs/architecture.md). Supported runtimes and library-support levels are defined in [docs/compatibility.md](docs/compatibility.md).

The first versioned IR is implemented as immutable Python models with deterministic dictionary and JSON round trips:

```python
json_text = facts.to_json()
restored = NotebookFacts.from_json(json_text)
```

The notebook loader now validates local Jupyter notebooks, rejects unsupported formats and non-Python notebooks with stable diagnostic codes, and returns normalized source cells without executing or analyzing notebook code.

Progress and architectural decisions are recorded chronologically in [JOURNAL.md](JOURNAL.md).

## Initial roadmap

1. [x] Formalize the supported notebook subset.
2. [x] Initialize the Python package and quality tooling.
3. [x] Implement the immutable intermediate representation and serialization.
4. [x] Load and validate notebooks.
5. [ ] Analyze cells with Python's AST.
6. [ ] Resolve cross-cell dependencies.
7. [ ] Generate a minimal Kedro project for controlled fixtures.
8. [ ] Verify equivalence through observable outputs.
9. [ ] Gradually add semantic planning, parameters, catalogs, and advanced diagnostics.

## Contributing

The project uses [uv](https://docs.astral.sh/uv/) for Python and dependency management.

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run pre-commit install
```

The committed `uv.lock` file defines the reproducible development and CI environment. See [docs/decisions/0001-use-uv.md](docs/decisions/0001-use-uv.md) for the decision record.

## Project name

**Notebook to Kedro** is a working name. The planned Python package name is `notebook_to_kedro`.
