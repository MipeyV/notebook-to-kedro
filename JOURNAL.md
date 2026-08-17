# Development Journal

This file provides a chronological record of **Notebook to Kedro** development.

It keeps track of:

- work that has actually been completed;
- architectural decisions and their rationale;
- limitations discovered along the way;
- unresolved questions;
- the next concrete step.

This journal is neither a release changelog nor a simple backlog. An entry is added when work is completed or a structural decision is made.

## Entry convention

New entries should follow this structure whenever possible:

```markdown
## YYYY-MM-DD — Short title

### Completed

- ...

### Decisions

- ...

### Open questions

- ...

### Next step

- ...
```

The newest entries are added at the top, immediately below this convention, so the current state remains easy to find.

---

## 2026-08-17 — Reference notebook made executable

### Completed

- Replaced the nonexistent CSV input in `simple_training.ipynb` with scikit-learn's bundled Iris dataset.
- Added a deterministic, stratified train/test split and fixed model random state.
- Added a minimum accuracy assertion to make silent workflow regressions visible.
- Executed the full notebook through a real Jupyter kernel without persisting generated outputs.
- Confirmed an accuracy of `0.9` and 30 predictions on the test split.
- Updated the facts schema examples to reflect the executable data-loading cell.

### Decisions

- The first fixture uses a bundled dataset so it remains deterministic and requires no runtime network access.
- Notebook execution validation is separate from static analyzer tests, which must never execute source code.
- A later fixture will exercise file-backed input and Kedro Data Catalog generation independently.
- Future notebook-to-Kedro equivalence tests will compare observable values such as predictions and metrics, not only successful execution.

### Open questions

- Define the exact equivalence policy for floating-point metrics, arrays, and tabular outputs.
- Select the file-backed dataset and dataset format for the Data Catalog fixture.
- Decide whether executed reference outputs should be stored as snapshots or recomputed in CI.

### Next step

- Initialize the Python package and reproducible test dependencies, then automate reference-notebook execution in the test suite.

## 2026-08-16 — Deterministic analysis contract specified

### Completed

- Defined the accepted, warned, and rejected notebook constructs for the first milestone.
- Defined the versioned `NotebookFacts` interchange schema.
- Documented source provenance, symbols, calls, dependencies, and diagnostics.
- Added `simple_training.ipynb` as the first reference fixture.
- Validated the fixture as Jupyter `nbformat` 4.5 JSON.
- Verified that all Python code cells parse successfully without being executed.

### Decisions

- Static source facts will be extracted deterministically before any LLM is invoked.
- `NotebookFacts` will be the canonical typed representation and JSON interchange format.
- DataFrames may be offered as inspection views but will not be the source of truth.
- A future semantic planner will produce a separate `ConversionPlan` without modifying source facts.
- Diagnostic codes will be treated as public API once released.

### Open questions

- Choose the concrete Python model implementation: standard-library dataclasses, Pydantic, or a combination of both.
- Decide how much nested-scope detail belongs in schema version 1.0.
- Define the unsupported notebook fixtures required for each initial diagnostic code.

### Next step

- Initialize the Python package and quality tooling, then encode the documented IR as typed models.

## 2026-08-16 — English adopted as the project language

### Completed

- Translated the project documentation from French to English.
- Kept the MIT license in English.

### Decisions

- English is now the default language for documentation, source code, comments, diagnostics, commit messages, and future project artifacts.

### Open questions

- None for this documentation change.

### Next step

- Initialize the Python package skeleton and specify the first notebook fixtures before implementing the loader.

## 2026-08-16 — Project initialization

### Completed

- Clarified the target problem: automate the transition from a reasonably clean Data Science notebook to a structured Kedro project.
- Defined the initial functional scope and MVP boundaries.
- Proposed a staged architecture: loading, AST analysis, dependency resolution, intermediate representation, Kedro generation, and filesystem writing.
- Identified the primary risks: implicit state, mutations, side effects, Python scopes, parameter inference, and Kedro compatibility.
- Created `README.md` with the project context, goals, scope, and initial roadmap.
- Created this development journal.
- Initialized the local Git repository with `main` as its primary branch.
- Added the open-source MIT license.
- Created and connected the public `MipeyV/notebook-to-kedro` GitHub repository.

### Decisions

- The MVP will not depend on an LLM.
- The intermediate representation will remain separate from the Kedro generator.
- Initially, one convertible code cell will map to at most one task; automatic cell merging is deferred.
- Ambiguous cases must produce explicit diagnostics and may block generation.
- The first implementation milestone will focus on notebook analysis rather than Kedro generation.
- Generated Kedro projects will target an explicitly defined and tested version.

### Open questions

- Choose the minimum supported Python and Kedro versions.
- Define the exact matrix of supported, warned, and rejected constructs.
- Finalize the intermediate representation models.
- Choose a convention for explicit parameter extraction.
- Decide on the final project name and verify its availability before any package publication.

### Next step

- Initialize the Python package skeleton and specify the first notebook fixtures before implementing the loader.
