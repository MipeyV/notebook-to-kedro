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

The intended conversion contract is:

1. preserve the notebook cells, source code, and dependencies as traceable static facts;
2. represent the workflow as explicit steps with inputs, outputs, parameters, diagnostics, and source provenance;
3. propose code for each step as a Kedro node without silently changing the notebook's behavior;
4. validate and expose the complete plan for human review before writing the project;
5. compare observable notebook and Kedro outputs whenever the workflow can be executed safely.

The generated project may improve structure, naming, configuration, and separation of responsibilities. It must not invent new business logic or silently optimize away behavior from the source notebook.

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

## Project status

The deterministic V1 pipeline is operational for the supported notebook subset. It can analyze a notebook, build and validate a reviewable conversion plan, render a Markdown report, and generate a minimal Kedro project whose observable outputs are checked against reference notebooks.

Development is now moving from the deterministic foundation toward V2 hybrid semantic planning and broader notebook coverage. The deterministic path will remain available as the default and as the fallback for every future provider integration.

The first [node code generation contract](docs/node-code-contract.md) is available as an offline
Python API: versioned task requests, strict JSON responses, a provider protocol, a fake provider,
and static validation of function signatures, imports, global references, and returns. Accepted
proposals are not yet executed or written into generated projects; behavioral equivalence and
the Ollama code-generation adapter are subsequent steps.

The initial deterministic analysis contract is documented in [docs/mvp-contract.md](docs/mvp-contract.md), and its interchange model is defined in [docs/notebook-facts-schema.md](docs/notebook-facts-schema.md).

The first reference fixture runs a deterministic Iris classification workflow. It provides a known-good baseline whose predictions and accuracy can later be compared with the generated Kedro pipeline.

The planned module boundaries and test strategy are described in [docs/architecture.md](docs/architecture.md). Supported runtimes and library-support levels are defined in [docs/compatibility.md](docs/compatibility.md).

The first versioned IR is implemented as immutable Python models with deterministic dictionary and JSON round trips:

```python
json_text = facts.to_json()
restored = NotebookFacts.from_json(json_text)
```

The notebook loader now validates local Jupyter notebooks, rejects unsupported formats and non-Python notebooks with stable diagnostic codes, and returns normalized source cells without executing or analyzing notebook code.

The analyzer extracts imports, top-level statements, reads, writes, calls, and blocking syntax diagnostics from loaded notebooks. It resolves cross-cell dependencies by linking reads to the most recent earlier data definition.

The package now exposes a public analysis entrypoint that loads a notebook path and returns deterministic `NotebookFacts`:

```python
from notebook_to_kedro import analyze_notebook_path

facts = analyze_notebook_path("notebooks/model.ipynb")
```

It also exposes a planning entrypoint that proposes Kedro-oriented task candidates without writing
project files. Deterministic planning is the default:

```python
from notebook_to_kedro import plan_notebook_path

plan = plan_notebook_path("notebooks/model.ipynb")
```

Hybrid planning must be selected explicitly and requires a downloaded local Ollama model:

```python
from notebook_to_kedro import PlannerMode, plan_notebook_path

plan = plan_notebook_path(
    "notebooks/model.ipynb",
    planner=PlannerMode.HYBRID,
    ollama_model="your-local-model",
)
```

`create_semantic_planner` can be used separately when an application wants to construct and reuse
a planner. A custom object implementing `SemanticPlanner` can still be injected directly.

The package can render a deterministic Markdown report from a plan so reviewers can inspect the proposed nodes, catalog datasets, parameters, and blocking diagnostics before generation:

```python
from notebook_to_kedro import render_conversion_report

report = render_conversion_report(plan)
```

Plans can also be validated explicitly before generation:

```python
from notebook_to_kedro import validate_conversion_plan

validate_conversion_plan(plan)
```

The same static review flow is available from the command line:

```bash
notebook-to-kedro plan notebooks/model.ipynb
```

After reviewing the plan, the CLI can generate the minimal Kedro project:

```bash
notebook-to-kedro generate notebooks/model.ipynb generated/model_project
```

Expected notebook loading and generation failures are reported as concise CLI errors on stderr with a non-zero exit code.

The first Kedro generator writes an importable minimal project skeleton from a `ConversionPlan`:

```python
from notebook_to_kedro import generate_kedro_project

generate_kedro_project(plan, "generated/model_project")
```

The end-to-end suite now executes the generated Kedro pipeline for the reference Iris notebook and compares its final accuracy with the notebook output.

The planner recognizes simple `pd.read_csv("...")` assignments as catalog inputs. The generator writes a minimal `conf/base/catalog.yml` for those CSV-backed datasets and copies the source CSV into the generated project's `data/01_raw/` directory.

The planner also extracts selected literal scikit-learn parameters, and the generator writes `conf/base/parameters.yml` while wiring nodes with Kedro `params:` inputs.

Generated node names are now deterministic but reviewable: the planner uses nearby Markdown headings when available and falls back to simple source patterns such as `split_data`, `train_model`, `predict`, and `evaluate_model`.

The supported scikit-learn workflow now includes a simple `StandardScaler` preprocessing step using `fit_transform` and `transform`, with literal `with_mean` and `with_std` parameters extracted into Kedro configuration.

The planner recognizes simple pandas preprocessing steps such as `dropna`, `fillna`, and `assign` when they rewrite a dataframe variable, producing reviewable node names like `clean_data`, `impute_missing_values`, and `engineer_features`.

The planner also extracts selected literal pandas preprocessing parameters into Kedro configuration, including `fillna(value=...)`, positional `fillna({...})`, and `drop(columns=[...])`.

The planner also emits conversion diagnostics for review risks such as fallback names, inherited cell diagnostics, unresolved external inputs, and tasks without data outputs. These diagnostics are visible in the Markdown report and do not block generation unless the plan itself has blocking diagnostics.

Progress and architectural decisions are recorded chronologically in [JOURNAL.md](JOURNAL.md).

## V1 roadmap: deterministic foundation

1. [x] Formalize the supported notebook subset.
2. [x] Initialize the Python package and quality tooling.
3. [x] Implement the immutable intermediate representation and serialization.
4. [x] Load and validate notebooks.
5. [x] Analyze cells with Python's AST.
6. [x] Resolve cross-cell dependencies.
7. [x] Plan minimal Kedro-oriented task candidates.
8. [x] Generate a minimal Kedro project skeleton for controlled fixtures.
9. [x] Verify reference fixture equivalence through observable outputs.
10. [x] Add a file-backed CSV fixture with minimal catalog generation.
11. [x] Extract selected literal parameters into Kedro configuration.
12. [x] Generate readable deterministic node names from headings and simple source patterns.
13. [x] Render a reviewable Markdown conversion report.
14. [x] Add a minimal CLI for planning and reporting.
15. [x] Add a CLI command for generating a Kedro project.
16. [x] Report expected CLI failures without stack traces.
17. [x] Validate conversion plans explicitly before CLI generation.
18. [x] Add reviewable conversion diagnostics to plans and reports.
19. [x] Support a simple `StandardScaler` preprocessing pattern.
20. [x] Support simple pandas preprocessing naming patterns.
21. [x] Extract selected literal pandas preprocessing parameters.

## V2 roadmap: LLM-assisted conversion

### Phase 1: planner boundary

1. [x] Introduce a provider-neutral `SemanticPlanner` protocol.
2. [x] Keep the current deterministic planner as the default implementation.
3. [x] Define versioned request and response contracts for semantic suggestions.
4. [x] Add explicit planner selection to the Python API and CLI.
5. [x] Seed a versioned planning evaluation corpus from the reviewed V1 fixtures.

### Phase 2: safe provider integration

1. [x] Implement a fake provider for deterministic prompt, parsing, and failure tests.
2. [x] Add an optional local Ollama adapter without adding an SDK dependency to the core package.
3. [ ] Require explicit consent before sending notebook content to a remote provider.
4. [ ] Define redaction, credential, timeout, retry, cost, and error-reporting policies.
5. [ ] Keep paid and nondeterministic provider tests outside the default CI workflow.

### Phase 3: hybrid planning

1. [ ] Use LLM suggestions for ambiguous naming, classification, and cell grouping.
2. [ ] Propose node code, parameters, datasets, and tests for transformations not covered by deterministic patterns.
3. [x] Merge suggestions only when they are compatible with static dependencies and plan invariants.
4. [x] Preserve source provenance and identify LLM-assisted decisions in the conversion report.
5. [x] Fall back cleanly to deterministic planning when the provider is disabled or fails.

### Phase 4: evaluation and broader coverage

1. [ ] Build a versioned corpus of representative notebooks beyond controlled fixtures.
2. [ ] Measure plan validity, generation success, behavioral equivalence, review corrections, latency, and cost.
3. [ ] Compare deterministic and hybrid results on the same corpus.
4. [ ] Expand deterministic pandas support for `rename`, `replace`, joins, and aggregations.
5. [ ] Add richer catalog formats and schema-aware diagnostics.
6. [ ] Define release thresholds for a supported V2 preview.

V2 is successful when hybrid planning improves useful notebook coverage without weakening the deterministic guarantees: no unreviewed code reaches generation, invalid plans are rejected, generated nodes remain traceable to source cells, and equivalence checks continue to protect observable behavior.

The provider boundary and its trust rules are documented in
[docs/semantic-planning-contract.md](docs/semantic-planning-contract.md).
The local transport and its loopback-only safety policy are documented in
[docs/ollama-provider.md](docs/ollama-provider.md).
Safe suggestion assembly and fallback behavior are documented in
[docs/hybrid-planning.md](docs/hybrid-planning.md).

Compare the deterministic planner with a downloaded local model on the reviewed corpus:

```bash
notebook-to-kedro benchmark tests/fixtures/evaluation/planning/v1 \
  --project-root . \
  --planners deterministic hybrid \
  --ollama-model your-local-model > planning-benchmark.json
```

The versioned JSON report records corpus hashes, structural accuracy, deterministic plan validity,
fallback usage, and wall-clock planning latency. Live Ollama benchmarking is opt-in and remains
outside the default test suite. The report contract and current limitations are documented in
[docs/planning-evaluation-corpus.md](docs/planning-evaluation-corpus.md).

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

Release history is recorded in [CHANGELOG.md](CHANGELOG.md). Maintainers should follow the
[release process](docs/releasing.md) when preparing tags and GitHub artifacts.

## Project name

**Notebook to Kedro** is a working name. The planned Python package name is `notebook_to_kedro`.
