# Project overview

[Documentation index](../README.md)

Status: original design and scope, extracted from the root README on 2026-10-11.
This includes target interfaces and future design, not just implemented features.
Use the compatibility reference and current project status for supported behavior.

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

The intended conversion contract is:

1. preserve the notebook cells, source code, and dependencies as traceable static facts;
2. represent the workflow as explicit steps with inputs, outputs, parameters, diagnostics, and source provenance;
3. propose code for each step as a Kedro node without silently changing the notebook's behavior;
4. validate and expose the complete plan for human review before writing the project;
5. compare observable notebook and Kedro outputs whenever the workflow can be executed safely.

The generated project may improve structure, naming, configuration, and separation of responsibilities. It must not invent new business logic or silently optimize away behavior from the source notebook.

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

## V2: hybrid semantic planning

V2 will add an optional LLM-assisted planner around the deterministic core. The LLM will not parse notebooks, write directly to the destination, or replace validation. It will receive structured notebook facts and propose a structured plan that remains reviewable and traceable to the original cells.

```text
Notebook .ipynb
      |
      v
Deterministic loading, AST analysis, and dependency resolution
      |
      v
Versioned notebook facts + deterministic baseline plan
      |
      v
Hybrid semantic planner
  - deterministic rules
  - optional LLM suggestions for ambiguous steps
      |
      v
Validated ConversionPlan + human-readable report
      |
      v
Deterministic Kedro generator
      |
      v
Generated project + equivalence checks
```

The hybrid planner may assist with:

- domain-aware node naming and block classification;
- grouping multiple related cells into coherent pipeline steps;
- identifying inputs, outputs, datasets, and parameters when static evidence is ambiguous;
- refactoring complex imperative code into focused node functions;
- explaining conversion risks and suggesting tests.

Static evidence remains authoritative. Every LLM proposal must use a versioned structured response, preserve source-cell provenance, pass deterministic validation, and appear in the conversion report before generation. Invalid or unavailable LLM output must produce an actionable diagnostic or fall back to the deterministic plan.

The default mode remains fully local and deterministic. Hybrid mode will be explicit and opt-in because notebook code and metadata may be sensitive. Provider configuration, redaction rules, timeouts, cost visibility, and local-model support belong to the provider boundary rather than the core analyzer or generator.
