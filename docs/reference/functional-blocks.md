# Functional block inspection

[Documentation index](../README.md)

Status: first E2 analysis slice, implemented on 2026-11-06. Kedro generation from this
representation and behavioral comparison of the paired inputs remain the next slice.

## Usage

```bash
uv run notebook-to-kedro inspect-blocks examples/functional_blocks/workflow.py
uv run notebook-to-kedro inspect-blocks examples/functional_blocks/workflow.ipynb
```

```python
from notebook_to_kedro import analyze_functional_blocks_path

analysis = analyze_functional_blocks_path("examples/functional_blocks/workflow.py")
print(analysis.to_json())
```

The command writes JSON to stdout, including retained source and diagnostics. It returns 0
when inspection is complete for the supported subset, or 1 for blockers. Load errors go to
stderr and return 1. It does not execute source, import its dependencies, contact a provider
or write a project. Treat exported JSON as source code when sharing it.

## Contracts and provenance

`analysis.functional.analyze_functional_blocks` is a pure analyzer of ordered `SourceUnit`
values from `ir.functional`. Unit IDs must be unique. Filesystem adapters return the same
`FunctionalAnalysis` without fabricating notebook cells for Python files:

- A `.py` file is one module unit. Its bytes are read once, bounded to 1 MiB, hashed and
  decoded using Python's encoding declaration/BOM rules. Captured text retains line endings.
- An `.ipynb` uses the existing Python notebook loader and real code cells in physical order.
  Markdown/raw cells are outside Python inspection. The loader's `cell-000N` IDs identify
  physical positions, rather than editable JSON cell IDs. Recorded execution counts are not
  execution order. Existing notebook loading limits apply; the Python-file bound does not.
- Paths are relative to the selected project root when contained, otherwise absolute POSIX
  paths. Units record the document SHA-256 and a separate SHA-256 of captured decoded UTF-8
  text. The notebook loader reads document bytes and parsed content separately: these hashes
  are provenance, not an atomic concurrent-file snapshot or authenticated evidence.

Every parsed top-level statement records exact source, an attribute-free AST hash and a span,
including unsupported statements. Invalid units retain their entire source with a diagnostic.
Spans use one-based lines and zero-based UTF-8 byte columns; notebook lines are cell-local.
Function source/spans include decorators even when unsupported. Comments and whitespace remain
in unit text; comments are not AST statements.

`FunctionalBlock` records function names, parameter names, named return values, global reads,
syntactic call targets and possible receiver mutations for known fit methods. Dependencies
connect references to uniquely named module functions, distinguishing direct calls from other
references. This is a function-reference graph, not a Kedro dataset DAG. Function arguments
are not inferred `parameters.yml` entries. Return names do not establish dataset ownership,
runtime types or schemas. Calls do not establish actual object identity.

## Initial supported subset

The first slice covers library-style, single-file Python and equivalent function-based notebooks:
absolute explicitly named imports, leading module/cell docstrings and synchronous top-level
functions. Functions have ordinary positional parameters and straight-line assignments,
assertions, expressions/calls and exactly one final return of a name or nonempty tuple of names.
Local reads must follow binding. An annotation without a value does not bind a local name.
Non-call annotations are retained with a warning; types and definition-time behavior are unverified.

Blockers cover syntax/compile errors, module-level executable code (including a main guard),
ambiguous imports or definitions, relative/star imports, decorators, defaults, positional-only,
keyword-only/variadic/generic signatures, annotation calls, unsupported returns, control flow,
nested definitions, comprehensions and other deferred/dynamic expressions, attribute/subscript
writes, unresolved globals, recursion/cycles and indirect/local callable targets. This slice
does not split procedural cells automatically, reconstruct multi-file projects or infer catalog
I/O. Function calls can still have external effects; their presence always warns.

| Code | Meaning |
| --- | --- |
| BL001 | Invalid Python syntax or compilation context. |
| BL002 | Unsupported or ambiguous module-level statement/binding. |
| BL003 | Unsupported function signature or return contract. |
| BL004 | Unsupported body construct, mutation write or dynamic namespace call. |
| BL005 | Unresolved global names in a function. |
| BL006 | Local read before a supported straight-line binding. |
| BL007 | Cyclic function references. |
| BL008 | Indirect/local callable target. |
| BL009 | No explicit synchronous functions found. |
| BL101 | Call effects and identities are unverified (warning). |
| BL102 | Known fit-method pattern may mutate the receiver (warning). |
| BL103 | Annotations are retained but unverified (warning). |

`complete` means at least one block and no error diagnostics for this inspection subset. It
does not approve execution, establish equivalence, validate business intent or permit generation.
Unsupported code is retained and reported rather than repaired or omitted.

## Paired example and fingerprint

The committed [script](../../examples/functional_blocks/workflow.py) and
[notebook](../../examples/functional_blocks/workflow.ipynb) contain identical function/import ASTs.
Tests require the same `structure_sha256`, interfaces and call edges, while preserving distinct
paths, lines, cells and document hashes. Whitespace changes preserve the fingerprint; a body
logic change alters it. The fingerprint excludes source origins/text and module documentation,
but includes ordered import/function AST hashes, function metadata and dependencies. It is absent
for blocked analyses. It is an ordered static identity, not a behavioral proof or general
semantic-equivalence metric.

Existing `NotebookFacts`, `ConversionPlan`, `plan` and `generate` contracts remain separate.
The analyzers share small AST naming/constants utilities; functional inspection does not bypass
notebook source accounting or make a `.py` file eligible for Kedro generation. Next define
entrypoint/data wiring and source accounting, then compare generated Kedro behavior from both
presentations using reviewed observable contracts.
