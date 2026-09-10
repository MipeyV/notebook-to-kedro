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

## 2026-09-10 — Cell-level AST analysis implemented

### Completed

- Added a deterministic AST analyzer that consumes `LoadedNotebook` and returns `NotebookFacts`.
- Preserved non-code cells while extracting code-cell statements, imports, calls, reads, and writes.
- Recorded regular imports, from-imports, function definitions, class definitions, assignments, tuple/list unpacking writes, attribute reads, subscript reads, ordinary calls, and method calls.
- Added blocking diagnostics for invalid Python syntax, Jupyter magics, shell escapes, and dynamic execution calls.
- Added mutation warnings for known estimator-style mutating method calls such as `fit`.
- Categorized discovered symbols as imports, data, functions, classes, or unknown reads.
- Added unit tests for AST extraction and an integration test for the reference Iris notebook analysis.
- Reached 100% statement and branch coverage with 112 passing tests.

### Decisions

- The analyzer returns `NotebookFacts` with empty dependency facts until cross-cell dependency resolution is implemented.
- Cell-level reads include unresolved names as `unknown` symbols rather than emitting unresolved-dependency diagnostics in this increment.
- Calls are represented syntactically; referenced notebook packages are never imported by the analyzer.
- The initial mutation heuristic is deliberately narrow and currently covers selected estimator-style methods.

### Open questions

- Decide how broad the first mutation and side-effect heuristic should be beyond estimator-style method calls.
- Decide whether unresolved local reads should emit `DF001` during symbol construction or only after dependency resolution.
- Define how function body free variables should be reported once scope analysis is introduced.

### Next step

- Implement cross-cell symbol and dependency resolution from the collected cell-level reads and writes.

## 2026-09-10 — Notebook loader implemented

### Completed

- Added a notebook loading boundary with immutable source models for loaded notebooks and cells.
- Loaded notebooks through `nbformat` without converting their declared notebook format version.
- Validated that notebooks use `nbformat` major version 4 and are identified as Python through language metadata or kernelspec metadata.
- Preserved physical cell order, cell source, execution counters, kernel name, relative POSIX path, and source-content SHA-256.
- Added stable `NB001` and `NB002` loader errors for unsupported loading and language cases.
- Added unit tests for successful loading, rejected notebooks, defensive loader validation, and immutable loaded source models.
- Reached 100% statement and branch coverage with 98 passing tests.

### Decisions

- The loader returns notebook source models rather than `NotebookFacts`; AST analysis remains a separate component.
- Notebook format validation uses `nbformat.NO_CONVERT` so unsupported major versions are not silently upgraded during loading.
- Loader cell IDs are derived from physical source order instead of trusting optional notebook cell IDs.
- Paths emitted by the loader are relative to the selected project root when possible, with a file-name fallback outside that root.

### Open questions

- Decide whether loader errors should later be converted directly into `Diagnostic` records or remain exception-first until partial facts are available.
- Decide which notebook metadata fields beyond language and kernel should be preserved for semantic planning.

### Next step

- Implement cell-level AST analysis for supported Python code cells without resolving cross-cell dependencies yet.

## 2026-08-17 — NotebookFacts intermediate representation implemented

### Completed

- Implemented frozen, slotted dataclasses for notebook metadata, cells, statements, imports, calls, symbols, dependencies, and diagnostics.
- Added explicit enums for cell, import, symbol, and diagnostic categories.
- Enforced local and document-wide invariants at construction time.
- Implemented deterministic dictionary and JSON serialization.
- Implemented validated deserialization from dictionaries and JSON.
- Added unit and contract tests covering the complete public interchange schema.
- Reached 100% statement and branch coverage with 62 passing tests.

### Decisions

- The IR uses standard-library dataclasses rather than Pydantic for the deterministic core.
- Source facts are immutable after construction.
- Diagnostic blocking behavior is explicit and independent from severity.
- Notebook paths are relative and use POSIX separators in serialized output.
- Arbitrary nested diagnostic metadata is deferred; schema 1.0 supports immutable JSON primitives.
- Deserialization of `NotebookFacts` subclasses is rejected until an extension contract exists.

### Open questions

- Determine whether future schema versions need nested diagnostic detail values.
- Define the migration policy before publishing a second schema version.
- Decide which notebook metadata fields beyond kernel and language are relevant to semantic planning.

### Next step

- Implement the notebook loader that validates `nbformat` 4 Python notebooks and produces normalized cell source models without AST analysis.

## 2026-08-17 — Project architecture and uv tooling initialized

### Completed

- Documented the source-module boundaries, dependency direction, and test architecture.
- Defined Python, Kedro, notebook-format, and library-support compatibility levels.
- Recorded uv adoption in the first architecture decision record.
- Installed uv 0.12.5 and generated the cross-platform `uv.lock` file.
- Created the `src/` package skeleton with typed-package metadata.
- Configured Hatchling, Ruff, strict mypy, pytest, coverage, and pre-commit.
- Added unit and integration test directories with automated Iris notebook execution.
- Added a GitHub Actions matrix for Python 3.11, 3.12, and 3.13.
- Built the source distribution and wheel successfully.

### Decisions

- Python 3.12 is the primary development and strict-typing version.
- The initial compatibility matrix covers Python 3.11 through 3.13.
- The published runtime depends only on `nbformat`; ML and Kedro packages remain test dependencies.
- Kedro `>=1.5,<2` is the initial generated-project compatibility target.
- CI runs deterministic tests across the Python matrix and the complete integration suite on Python 3.12.
- GitHub Actions use a pinned `setup-uv` commit and a fixed uv version.
- Line endings are normalized to LF for source, configuration, documentation, and notebook files.

### Open questions

- Decide when Python 3.10 and 3.14 should enter the compatibility matrix.
- Define the first typed `NotebookFacts` implementation without prematurely adding Pydantic.
- Add a second file-backed notebook fixture for Data Catalog coverage.

### Next step

- Implement the immutable `NotebookFacts` domain models and their deterministic JSON serialization.

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
