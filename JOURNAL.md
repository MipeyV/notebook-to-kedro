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

## 2026-09-11 - Conversion report renderer implemented

### Completed

- Added `render_conversion_report(plan)` as a public API.
- Rendered deterministic Markdown summaries for conversion plans.
- Included proposed task candidates with source cells, inputs, outputs, parameters, and diagnostics.
- Included catalog datasets, extracted parameters, and blocking diagnostic codes.
- Added Markdown escaping for table-sensitive values.
- Covered complete, empty, blocked, and escaping cases in unit tests.
- Reached 100% statement and branch coverage with 148 passing tests.

### Decisions

- The first report format is Markdown because it is readable in terminals, PRs, and docs.
- Reporting depends only on `ConversionPlan`; it does not import Kedro or re-read notebooks.
- Empty sections are explicit instead of omitted so reviewers can distinguish "none found" from missing output.

### Open questions

- Decide whether future reports should include diagnostic messages, not only codes.
- Decide whether to add JSON report output for machines and CI annotations.
- Decide how the future CLI should write or print reports.

### Next step

- Add a minimal CLI for planning/reporting so a user can run the static review flow from a notebook path.

## 2026-09-11 - Readable deterministic node names implemented

### Completed

- Added deterministic task naming before parameter extraction.
- Derived task names from recognized source patterns such as split, train, predict, evaluate, and load.
- Used the nearest preceding Markdown heading as a fallback naming signal.
- Kept generated names as valid Python identifiers and made duplicates deterministic with numeric suffixes.
- Renamed extracted parameter keys to follow the readable node names, such as `split_data.test_size`.
- Updated unit, integration, generation, and end-to-end expectations.
- Reached 100% statement and branch coverage with 143 passing tests.

### Decisions

- Source patterns take precedence over Markdown headings because they are tied to executable evidence.
- Markdown headings are still useful review signals for transformation cells without recognized library calls.
- `cell_0000` remains the final fallback when no reliable semantic cue exists.

### Open questions

- Decide whether to expose naming confidence or provenance in `ConversionPlan`.
- Add richer transformation naming beyond the current ML workflow patterns.
- Decide when a naming proposal should require human review instead of being accepted automatically.

### Next step

- Add conversion report output so users can review planned nodes, parameters, catalog inputs, and diagnostics before trusting the generated project.

## 2026-09-11 — Selected Kedro parameter extraction implemented

### Completed

- Added `ParameterValue` records to `ConversionPlan`.
- Extracted literal parameters from supported scikit-learn calls:
  `train_test_split(test_size=..., random_state=...)` and
  `RandomForestClassifier(n_estimators=..., random_state=...)`.
- Attached extracted parameter names to their task candidates.
- Generated `conf/base/parameters.yml` for extracted values.
- Rewrote generated node code to use function arguments instead of hardcoded keyword literals.
- Wired generated Kedro nodes with `params:<name>` inputs.
- Updated end-to-end tests to load generated parameters into the in-memory Kedro catalog.
- Reached 100% statement and branch coverage with 141 passing tests.

### Decisions

- The first parameter extraction pass is deterministic and limited to literal JSON-compatible values.
- Parameter keys are cell-scoped, such as `cell_0006.test_size`, until semantic node naming exists.
- Unsupported or non-literal keyword values remain in source code rather than being guessed.

### Open questions

- Decide how reviewed semantic node names should rename parameter keys.
- Decide whether repeated parameter values should be deduplicated across nodes.
- Extend parameter extraction to pandas and user-defined transformation thresholds.

### Next step

- Generate more reviewable node names from notebook headings or simple source patterns.

## 2026-09-11 — File-backed CSV catalog fixture implemented

### Completed

- Added a second reference notebook that loads a local CSV with `pd.read_csv`.
- Added a small deterministic tabular classification CSV fixture.
- Extended `ConversionPlan` with proposed catalog datasets.
- Detected simple `pd.read_csv("...")` assignments as CSV catalog inputs.
- Skipped CSV loading cells when creating task candidates so generated nodes consume catalog inputs.
- Generated `conf/base/catalog.yml` entries with `kedro_datasets.pandas.CSVDataset`.
- Copied detected source CSV files into the generated project's `data/01_raw/` directory.
- Added unit, integration, and end-to-end coverage for the file-backed workflow.
- Verified that the generated Kedro pipeline matches the source notebook final accuracy for the CSV-backed fixture.

### Decisions

- The first catalog pattern requires a literal string filepath in a direct `read_csv` assignment.
- The generated project declares `kedro-datasets[pandas]` when CSV catalog support is used.
- End-to-end tests still execute with in-memory datasets while loading the generated-project copy of the CSV.

### Open questions

- Add support for parameter extraction before broadening catalog formats.

### Next step

- Extract simple literal parameters such as `test_size`, `random_state`, and `n_estimators` into a generated `parameters.yml`.

## 2026-09-10 — Generated pipeline equivalence test implemented

### Completed

- Added an end-to-end test for the reference notebook-to-Kedro path.
- Executed the source notebook with `nbclient` to obtain the expected final accuracy.
- Generated a Kedro project from `plan_notebook_path` and `generate_kedro_project`.
- Imported the generated pipeline package from the temporary project source tree.
- Ran the generated Kedro pipeline with `SequentialRunner` and in-memory datasets.
- Compared the generated pipeline's final `accuracy` output with the executed notebook output.
- Reached 100% statement and branch coverage with 130 passing tests.

### Decisions

- The first equivalence check compares the final accuracy because it is the stable observable output already exposed by the reference notebook.
- The generated pipeline is executed in memory to avoid introducing catalog files before the file-backed dataset fixture exists.
- Intermediate predictions are not compared yet because Kedro may release intermediate in-memory datasets after execution.

### Open questions

- Decide which intermediate artifacts should be persisted or captured for richer equivalence checks.
- Add a file-backed fixture before implementing catalog generation.
- Decide how to separate fast default tests from heavier end-to-end validation as the suite grows.

### Next step

- Add a second fixture with file-backed tabular input and generate a minimal Kedro catalog for it.

## 2026-09-10 — Minimal Kedro project skeleton generator implemented

### Completed

- Added a Kedro generation boundary that consumes `ConversionPlan`.
- Generated a minimal project skeleton with `pyproject.toml`, package files, pipeline registry, nodes, and pipeline definition.
- Rendered task candidates as node functions while preserving source code and notebook imports.
- Remapped repeated symbol outputs to unique Kedro dataset names such as `df__cell_0005`.
- Rejected existing destinations to avoid silent overwrites.
- Rejected generation when blocking diagnostics are present.
- Exposed `generate_kedro_project` through the package-level API.
- Added tests that import the generated Kedro pipeline and verify the reference fixture produces six nodes.

### Decisions

- The first generator targets an importable skeleton before running a full Kedro project.
- Generated project dependencies include Kedro, pandas, and scikit-learn for the controlled reference fixture.
- Dataset names are derived from source symbols, with version suffixes only when a symbol is redefined.
- Catalog generation, parameter extraction, and project execution are deferred to later increments.

### Open questions

- Decide how generated projects should declare catalog entries for file-backed datasets.
- Decide how task candidates should be reviewed or renamed before rendering production node names.
- Decide whether mutable estimator flows should remain single-cell nodes or become explicit train/predict abstractions.

### Next step

- Add an end-to-end fixture that executes the generated Kedro pipeline and compares observable outputs with the source notebook.

## 2026-09-10 — Minimal task planner implemented

### Completed

- Added immutable `ConversionPlan` and `TaskCandidate` contracts for proposed Kedro-oriented tasks.
- Added a deterministic `plan_tasks` planner that creates one task candidate per analyzable code cell with data outputs.
- Skipped markdown, raw, empty, and import-only cells.
- Derived task inputs from resolved dependencies plus unresolved non-import reads that still require review.
- Exposed `plan_notebook_path` as a package-level API that loads, analyzes, and plans a notebook path.
- Added unit and integration coverage for planning the reference notebook.

### Decisions

- The first planner is deterministic and does not use an LLM.
- Planning stops when blocking diagnostics are present in the source facts.
- Task names are stable cell-derived identifiers until semantic naming is introduced.
- The planner proposes task boundaries only; Kedro files are not generated in this increment.

### Open questions

- Decide how task candidates should be reviewed and renamed before generation.
- Decide how imports should be represented in the future generated module.
- Decide whether adjacent code cells should be merged before Kedro node generation.

### Next step

- Implement minimal Kedro project generation from reviewed task candidates for the controlled reference fixture.

## 2026-09-10 — Public analysis API implemented

### Completed

- Added `analyze_notebook_path` as the package-level entrypoint for loading and analyzing a notebook path.
- Reused the existing validated notebook loader and deterministic analyzer instead of adding a separate analysis path.
- Added unit coverage for the root package export.
- Added integration coverage for analyzing the reference notebook through the public API.

### Decisions

- The public API accepts file paths while the lower-level analyzer continues to accept an already loaded notebook model.
- The API returns `NotebookFacts` directly so downstream planning and reporting can build on the same canonical IR.
- CLI commands and human-readable reports remain out of scope for this increment.

### Open questions

- Decide whether the first user-facing report should be JSON-only, Markdown, or a typed report model.
- Decide how loader exceptions should be surfaced once a CLI or conversion report exists.

### Next step

- Implement a minimal task planner that groups analyzable code cells into Kedro-oriented task candidates without generating project files yet.

## 2026-09-10 — Cross-cell dependency resolution implemented

### Completed

- Added a dependency resolver that links a statement read to the most recent earlier data definition in physical cell order.
- Integrated dependency resolution into the deterministic analyzer output.
- Kept same-cell reads represented as statement facts without producing cross-cell dependency edges.
- Ignored imported names as dependency producers while still satisfying reads of imported bindings.
- Added `DF001` diagnostics for reads without a known producer or import binding.
- Added `DF002` diagnostics for repeated top-level data definitions.
- Updated the reference notebook analysis integration test to assert reviewed dependency symbols.
- Reached 100% statement and branch coverage with 116 passing tests.

### Decisions

- Dependency facts are cross-cell edges only because the current IR requires producer cells to precede consumer cells.
- The resolver uses physical source order and does not inspect execution counters or runtime object identity.
- Imported names remain symbol facts of kind `import` but do not produce dependency facts.
- Same-statement writes do not satisfy reads from that same statement.

### Open questions

- Decide whether same-cell producer/consumer relationships need their own fact type in a future schema version.
- Decide when execution counter inconsistency should emit `NB003`.
- Refine unresolved-read handling once local scope and function-body free-variable analysis are implemented.

### Next step

- Implement an analysis report or public `analyze` API that loads a notebook path and returns `NotebookFacts`.

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
