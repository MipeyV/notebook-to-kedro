# MVP Contract

## Purpose

The first Notebook to Kedro milestone converts a Python notebook into a deterministic, inspectable representation of static facts.

It does **not** generate Kedro code and does **not** use an LLM. Its output is the stable boundary that a future semantic planner will consume.

```python
facts = analyze_notebook("simple_training.ipynb")
payload = facts.to_json()
```

## Input contract

The analyzer accepts a single local `.ipynb` file that:

- conforms to Jupyter `nbformat` major version 4;
- declares a Python kernel or Python language metadata;
- contains syntactically valid Python code cells;
- is intended to execute from top to bottom;
- does not rely on state omitted from the notebook;
- uses ordinary Python names to pass values between cells.

Markdown and raw cells are preserved for provenance and future semantic analysis, but only Python code cells are parsed with the AST.

## Output contract

Successful analysis returns `NotebookFacts`, as defined in [notebook-facts-schema.md](notebook-facts-schema.md).

The result must be:

- deterministic for identical notebook content and analyzer version;
- serializable without executing notebook code;
- traceable to exact cells and source ranges;
- explicit about incomplete or uncertain static observations;
- independent of Kedro and any LLM provider.

The analyzer reports facts, not business meaning. For example, it may report that `model.fit(...)` reads and may mutate `model`; it must not claim that the cell is a training node.

## Support policy

Every encountered construct is classified as **supported**, **warning**, or **rejected**.

### Supported in the first vertical slice

The first implementation will support:

- regular and aliased imports;
- assignments to simple names;
- tuple and list unpacking assignments;
- attribute and subscript reads;
- ordinary function and method calls;
- literal call arguments;
- function and class definitions as discoverable declarations;
- dependencies created by a name written in one cell and read in a later cell;
- Markdown and raw cells as preserved context;
- notebooks with empty cells.

Support means the construct is represented without a blocking diagnostic. It does not imply that all Python runtime behavior has been inferred.

### Accepted with warnings

The analyzer will preserve these constructs but emit a diagnostic because their dataflow or side effects may be incomplete:

- method calls that may mutate an existing object, such as `model.fit(...)`;
- subscript and attribute assignments, such as `df["x"] = values`;
- augmented assignments;
- repeated definitions of the same top-level name;
- file, network, database, or environment access detected through known calls;
- free variables referenced by a function body;
- star imports;
- decorators;
- control flow whose writes are conditional;
- `try`, `with`, comprehensions, generators, and context-dependent scopes.

Warnings remain part of the result and do not block fact serialization.

### Rejected in the MVP

Analysis fails with at least one blocking diagnostic for:

- malformed notebook JSON or unsupported `nbformat` versions;
- notebooks that do not identify Python as their language;
- Python syntax errors in code cells;
- Jupyter line or cell magics;
- shell escapes such as `!pip install ...`;
- `exec`, `eval`, `compile`, or direct mutation of `globals()` or `locals()`;
- embedded code written in another programming language;
- dynamically generated imports that cannot be represented statically.

Rejection means no conversion plan may be created. Diagnostics and all facts successfully collected before the failure should still be available when practical.

## Execution-order assumptions

The analyzer uses physical cell order as the canonical order. Execution counters are preserved as metadata but do not reorder cells.

If non-null execution counters contradict physical order, the analyzer emits a warning. The MVP does not reconstruct historical interactive state.

## Name and dependency rules

For the first vertical slice:

1. A top-level name assignment is a symbol write.
2. Loading a top-level name is a symbol read unless it is bound locally by the same scope.
3. Imports create bindings and are recorded separately from data writes.
4. A dependency links the most recent earlier producer of a name to a later consumer.
5. Built-ins do not create unresolved dependencies.
6. Imported names do not become pipeline datasets.
7. A read without a known producer, import, built-in, or local binding is unresolved and produces a diagnostic.
8. Attribute names are not treated as independent symbols: `model.fit` reads `model`, not a top-level name named `fit`.

These rules describe static name flow, not object identity or alias analysis.

## Safety and privacy

The deterministic analyzer must not:

- execute code from the notebook;
- import modules referenced by the notebook;
- open data paths found in code;
- send notebook content to a remote service;
- infer or expose environment secrets.

Future LLM integration will require an explicit policy for redaction, user consent, provider configuration, and local-only operation.

## Acceptance criteria for milestone 1

Milestone 1 is complete when:

1. the reference notebook loads successfully;
2. every cell is preserved in source order;
3. imports, reads, writes, calls, and simple dependencies match reviewed expectations;
4. the result validates against the documented schema;
5. JSON serialization is stable across repeated runs;
6. unsupported fixtures produce the expected diagnostic codes;
7. the implementation executes no notebook code;
8. unit and integration tests pass in CI.

## Explicit non-goals

Milestone 1 does not include:

- semantic node classification;
- automatic node boundaries;
- parameter extraction;
- source-code refactoring;
- Kedro project generation;
- notebook execution or output comparison;
- dependency version inference;
- LLM prompting, training, or fine-tuning.

## Initial diagnostic codes

| Code | Severity | Meaning |
| --- | --- | --- |
| `NB001` | error | The notebook cannot be loaded or validated. |
| `NB002` | error | The notebook is not identified as Python. |
| `NB003` | warning | Execution counters contradict physical cell order. |
| `PY001` | error | A code cell contains invalid Python syntax. |
| `PY002` | error | A Jupyter magic or shell escape is present. |
| `PY003` | error | Dynamic execution or namespace mutation is present. |
| `DF001` | warning | A name is read without a known producer or binding. |
| `DF002` | warning | A top-level name is redefined. |
| `DF003` | warning | An operation may mutate an existing object. |
| `DF004` | warning | A write occurs conditionally. |

Diagnostic codes are public API once released and should not be renamed casually.
