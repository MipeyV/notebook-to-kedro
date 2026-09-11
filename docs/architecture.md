# Architecture

## Objective

Notebook to Kedro is designed as a staged compiler assisted by an optional semantic planner:

```text
Notebook source
    → deterministic loading and static analysis
    → NotebookFacts
    → optional semantic planning
    → ConversionPlan
    → deterministic validation
    → Kedro generation
    → generated project validation
```

Each boundary has a typed contract. Source facts, semantic inferences, and accepted transformations must never be mixed in the same model.

## Design rules

- Notebook code is never executed by the static analyzer.
- The deterministic core has no dependency on Kedro or an LLM SDK.
- `NotebookFacts` contains observations only.
- `ConversionPlan` contains proposed semantic decisions and their evidence.
- Only a validated conversion plan may reach a generator.
- Generated files remain traceable to source cells and statements.
- Unsupported or ambiguous behavior is reported explicitly.
- Provider-specific integrations remain optional and replaceable.
- Filesystem writes protect existing destinations by default.

## Source layout

```text
src/notebook_to_kedro/
├── __init__.py
├── api.py
├── diagnostics.py
├── exceptions.py
├── notebook/
│   ├── __init__.py
│   ├── loader.py
│   └── models.py
├── analysis/
│   ├── __init__.py
│   ├── ast_analyzer.py
│   ├── calls.py
│   ├── dependencies.py
│   ├── scopes.py
│   └── symbols.py
├── ir/
│   ├── __init__.py
│   ├── facts.py
│   ├── plan.py
│   └── serialization.py
├── semantic/
│   ├── __init__.py
│   ├── planner.py
│   ├── protocol.py
│   └── validation.py
└── generation/
    ├── __init__.py
    ├── writer.py
    └── kedro/
        ├── __init__.py
        ├── generator.py
        ├── renderer.py
        ├── validator.py
        └── templates/
```

Directories are introduced only when their first implementation is added. Empty architectural placeholders are avoided.

## Public API

The package root will expose a deliberately small API:

```python
from notebook_to_kedro import analyze, convert
```

Initial milestone:

```python
facts = analyze_notebook_path("notebooks/model.ipynb")
plan = plan_notebook_path("notebooks/model.ipynb")
report = render_conversion_report(plan)
validate_conversion_plan(plan)
created_files = generate_kedro_project(plan, "generated/model_project")
```

Initial command-line entrypoint:

```bash
notebook-to-kedro plan notebooks/model.ipynb
notebook-to-kedro generate notebooks/model.ipynb generated/model_project
```

Target API:

```python
report = convert(
    input_path="notebooks/model.ipynb",
    output_path="generated/my_kedro_project",
)
```

`api.py` orchestrates the use cases. It must not contain AST traversal, prompt construction, or template-rendering logic.

## Components

### Notebook loading

`notebook/` owns the Jupyter boundary:

- validate the path and notebook format;
- load through `nbformat`;
- detect the declared language;
- preserve physical cell order and relevant metadata;
- normalize source into internal notebook models.

It does not perform semantic or AST analysis.

### Static analysis

`analysis/` is the deterministic frontend:

- parse Python code with the standard-library AST;
- discover imports, declarations, reads, and writes;
- model scopes and free variables;
- record syntactic calls without importing their packages;
- identify possible mutations and side effects;
- resolve cross-cell name dependencies;
- emit stable diagnostic codes.

Static analysis describes name flow. It does not claim runtime object identity or business intent.

### Intermediate representation

`ir/` owns the domain contracts.

`NotebookFacts` is immutable source evidence:

```text
cells
statements
imports
calls
symbols
dependencies
diagnostics
```

`ConversionPlan` is a separate semantic proposal:

```text
candidate nodes
source fragments
proposed inputs and outputs
parameters
confidence
assumptions
review status
```

Serialization must be deterministic and versioned. DataFrames may be exposed as inspection views but are not canonical storage.

### Semantic planning

`semantic/` interprets facts and proposes node boundaries. It depends on a provider-neutral protocol:

```python
class SemanticPlanner(Protocol):
    def create_plan(self, facts: NotebookFacts) -> ConversionPlan: ...
```

The first implementation and default tests use a deterministic fake or fixture-backed planner. Real LLM providers are optional adapters introduced only after the plan schema and validation rules are stable.

The semantic layer may propose but cannot silently override static evidence.

The deterministic planner assigns stable, valid Python identifiers to task candidates. It prefers recognized source patterns such as train/test split, model training, prediction, and evaluation, then falls back to the nearest preceding Markdown heading, and finally to a `cell_0000` style name when no semantic clue is available.

`semantic/validation.py` validates `ConversionPlan` invariants before generation. It rejects blocked plans, duplicate task or configuration names, invalid Python task identifiers, and task parameter references that do not resolve to extracted parameters.

### Kedro generation

`generation/kedro/` consumes only a validated `ConversionPlan`:

- refactor approved source fragments into functions;
- render the Kedro package and pipeline files;
- generate configuration and catalog entries;
- register the pipeline;
- validate generated Python and project structure.

Repetitive Kedro boilerplate is rendered deterministically. An optional code transformer may assist with complex source refactoring, but its output must pass deterministic validation.

### Reporting

`reporting.py` renders review artifacts from `ConversionPlan` without importing Kedro or reading notebook files. The first report format is deterministic Markdown covering summary metadata, proposed tasks, catalog datasets, extracted parameters, and blocking diagnostics.

### CLI

`cli.py` owns terminal argument parsing and delegates to the public API. It should remain thin: commands orchestrate existing use cases and write their results, while analysis, planning, reporting, and generation logic stay in their component modules. The initial commands render a review report and generate a minimal Kedro project from a notebook path.

Expected notebook loading and project generation failures are formatted by the CLI as concise stderr messages with a non-zero exit code. Unexpected programming errors are not swallowed.

### Filesystem writing

`generation/writer.py` handles side effects:

- reject existing destinations unless overwrite is explicit;
- write to a temporary sibling directory;
- publish only complete output;
- report created files;
- clean partial output after failure when safe.

## Dependency direction

Dependencies point inward toward the domain contracts:

```text
api
├── notebook → ir
├── analysis → ir
├── semantic → ir
└── generation → ir
```

Forbidden dependencies include:

- `ir` importing Kedro, Jupyter, or an LLM SDK;
- `analysis` importing `semantic` or `generation`;
- `semantic` importing the Kedro generator;
- the static analyzer importing packages referenced by a notebook;
- provider-neutral protocols importing provider SDKs.

## Test architecture

```text
tests/
├── unit/
│   ├── notebook/
│   ├── analysis/
│   ├── ir/
│   ├── semantic/
│   └── generation/
├── contract/
├── integration/
├── end_to_end/
├── fixtures/
│   ├── notebooks/
│   ├── expected_facts/
│   ├── expected_plans/
│   └── generated_projects/
└── conftest.py
```

### Unit tests

Unit tests are fast, isolated, and offline. They cover one behavior at a time and do not launch notebook kernels, call LLMs, or run Kedro projects.

### Contract tests

Contract tests protect versioned boundaries:

- JSON serialization;
- schema compatibility;
- diagnostic-code stability;
- provider response validation;
- generator input requirements.

### Integration tests

Integration tests exercise real component boundaries:

- load and analyze a complete notebook;
- execute a controlled notebook fixture;
- render and import a generated package;
- run a generated Kedro pipeline.

### End-to-end tests

End-to-end tests compare observable notebook and Kedro outputs:

- predictions;
- metrics with explicit numerical tolerances;
- dataset schemas and shapes;
- model behavior where stable serialization is possible.

Successful execution alone is insufficient evidence of equivalence.

### LLM tests

Default CI never performs a paid or nondeterministic external LLM call. It uses fixtures and fake providers to test prompts, structured responses, validation, and error handling.

External tests are opt-in and marked:

```python
@pytest.mark.external
@pytest.mark.llm
```

They require explicit credentials and run only in a protected workflow or manually.

## Delivery increments

1. [x] Project tooling and package skeleton.
2. [x] Typed `NotebookFacts` models and deterministic serialization.
3. [x] Notebook loader.
4. [x] Cell-level AST analysis.
5. [x] Cross-cell dependency resolution.
6. [x] Public analysis API.
7. [x] Deterministic task planning.
8. [x] Minimal Kedro project skeleton generation.
9. [x] Reference notebook-to-Kedro equivalence testing.
10. [x] File-backed CSV catalog fixture.
11. [x] Selected literal parameter extraction.
12. [ ] Optional real LLM provider integration.

Each increment must leave the repository linted, typed, tested, and documented.
