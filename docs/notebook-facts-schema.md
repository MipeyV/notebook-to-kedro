# Notebook Facts Schema

## Purpose

`NotebookFacts` is the canonical deterministic representation produced from a notebook. It separates facts extracted from source code from future semantic inferences and code transformations.

The in-memory implementation may use frozen dataclasses or validated models. JSON is the interchange format. DataFrames may be exposed as convenience views, but they are not the source of truth because many fields are nested and relational.

## Schema principles

- Every record has stable provenance.
- Source order is preserved explicitly.
- Static facts never contain invented business meaning.
- Uncertainty is represented by diagnostics, not hidden by defaults.
- Ordered collections remain ordered in JSON.
- Sets are serialized as sorted arrays for deterministic output.
- Missing information uses `null`; it is not replaced with an empty string.
- Schema evolution is controlled by `schema_version`.

## Top-level document

```json
{
  "schema_version": "1.0",
  "analyzer_version": "0.1.0",
  "notebook": {},
  "cells": [],
  "symbols": [],
  "dependencies": [],
  "diagnostics": []
}
```

### Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Version of this interchange contract. |
| `analyzer_version` | string | yes | Library version that produced the facts. |
| `notebook` | `NotebookMetadata` | yes | Source notebook identity and language metadata. |
| `cells` | array of `CellFacts` | yes | All cells in physical source order. |
| `symbols` | array of `SymbolFacts` | yes | Top-level bindings and their accesses. |
| `dependencies` | array of `DependencyFacts` | yes | Resolved cross-cell name dependencies. |
| `diagnostics` | array of `Diagnostic` | yes | Notebook-wide and aggregated diagnostics. |

Paths serialized in the document should use POSIX separators for portability. Absolute paths should not be included by default.

## `NotebookMetadata`

```json
{
  "path": "tests/fixtures/notebooks/simple_training.ipynb",
  "nbformat": 4,
  "nbformat_minor": 5,
  "language": "python",
  "kernel_name": "python3",
  "cell_count": 12,
  "content_sha256": "..."
}
```

`content_sha256` is computed from the original notebook bytes and provides source identity. It must not include an absolute path.

## `CellFacts`

```json
{
  "id": "cell-0003",
  "index": 3,
  "kind": "code",
  "execution_count": null,
  "source": "df = pd.read_csv(\"data/customers.csv\")",
  "statements": [],
  "reads": ["pd"],
  "writes": ["df"],
  "imports": [],
  "calls": [],
  "diagnostic_codes": []
}
```

### Rules

- `id` is derived from the zero-based cell index and is stable within a notebook.
- `kind` is one of `code`, `markdown`, or `raw`.
- `execution_count` preserves notebook metadata but has no effect on ordering.
- `source` is preserved exactly after the normalization performed by `nbformat`.
- `statements` is empty for non-code cells.
- `reads`, `writes`, and `imports` are convenient cell-level summaries derived from statement facts.
- summary arrays contain unique names ordered by first source occurrence.
- `diagnostic_codes` references diagnostics stored in the top-level collection.

## `SourceLocation`

```json
{
  "cell_index": 3,
  "start_line": 1,
  "start_column": 0,
  "end_line": 1,
  "end_column": 48
}
```

Lines are one-based and columns are zero-based, matching Python AST conventions. End positions are exclusive where the Python AST provides them. Cell-level diagnostics may set line and column fields to `null`.

## `StatementFacts`

```json
{
  "id": "cell-0003-stmt-0000",
  "index": 0,
  "ast_type": "Assign",
  "source": "df = pd.read_csv(\"data/customers.csv\")",
  "location": {},
  "reads": ["pd"],
  "writes": ["df"],
  "calls": ["cell-0003-call-0000"],
  "conditional": false
}
```

`index` is the statement's position among top-level statements in the cell. Nested statements retain their source locations but belong to their nearest top-level statement for the first schema version.

## `ImportFacts`

```json
{
  "kind": "from",
  "module": "sklearn.model_selection",
  "name": "train_test_split",
  "alias": null,
  "bound_name": "train_test_split",
  "location": {}
}
```

For `import pandas as pd`, `module` is `pandas`, `name` is `null`, and `bound_name` is `pd`.

## `CallFacts`

```json
{
  "id": "cell-0003-call-0000",
  "qualified_name": "pd.read_csv",
  "receiver": "pd",
  "method": "read_csv",
  "positional_argument_sources": ["\"data/customers.csv\""],
  "keyword_argument_sources": {},
  "literal_arguments": ["data/customers.csv"],
  "possible_mutation_targets": [],
  "location": {}
}
```

`qualified_name` is a syntactic representation, not a runtime-resolved Python object. Arbitrary argument values are never evaluated.

## `SymbolFacts`

```json
{
  "name": "X_train",
  "kind": "data",
  "definitions": [
    {
      "cell_index": 5,
      "statement_id": "cell-0005-stmt-0000"
    }
  ],
  "reads": [
    {
      "cell_index": 7,
      "statement_id": "cell-0007-stmt-0001"
    }
  ]
}
```

Initial `kind` values are:

- `data`: a top-level value assignment;
- `import`: a name bound by an import;
- `function`: a top-level function definition;
- `class`: a top-level class definition;
- `parameter`: a function or lambda parameter when represented locally;
- `unknown`: a read with no resolved binding.

These are syntactic categories, not semantic ML types.

## `DependencyFacts`

```json
{
  "id": "dep-0007",
  "symbol": "X_train",
  "producer": {
    "cell_index": 5,
    "statement_id": "cell-0005-stmt-0000"
  },
  "consumer": {
    "cell_index": 7,
    "statement_id": "cell-0007-stmt-0001"
  },
  "resolution": "most_recent_definition"
}
```

A dependency represents a name-flow edge. It does not imply serialization, object independence, or a future Kedro dataset.

## `Diagnostic`

```json
{
  "id": "diagnostic-0001",
  "code": "DF003",
  "severity": "warning",
  "message": "Method call may mutate 'model'.",
  "location": {},
  "related_symbol": "model",
  "details": {
    "qualified_call": "model.fit"
  }
}
```

### Rules

- `severity` is one of `info`, `warning`, or `error`.
- `message` is human-readable and written in English.
- `code` is stable and machine-readable.
- `details` contains JSON-compatible structured context.
- error diagnostics marked as blocking prevent semantic planning.

The implementation should include an explicit `blocking` boolean rather than infer it from severity if non-blocking errors are ever introduced.

## Expected facts for the reference notebook

The first fixture should demonstrate at least these dependencies:

```text
df (load cell)          → df (feature cell)
X, y (feature cell)     → train_test_split cell
X_train, y_train        → training cell
model (training cell)   → prediction cell
X_test                  → prediction cell
predictions, y_test     → evaluation cell
```

The call to `model.fit(X_train, y_train)` should produce a possible-mutation diagnostic for `model`. The later read by `model.predict(X_test)` provides evidence that the mutated object crosses a cell boundary.

## Future semantic layer

A semantic planner must produce a separate `ConversionPlan`; it must never overwrite `NotebookFacts`.

Future inferred records should include:

- the originating fact identifiers;
- the model and prompt configuration used;
- confidence and rationale;
- proposed node boundaries;
- proposed names, inputs, outputs, and parameters;
- validation and human-review status.

This separation preserves the distinction between source facts, model inference, and accepted transformation decisions.
