# Explicit notebook dataset types

[Documentation index](../README.md)

## Scope

Notebook conversion can apply operator-declared dataset types to generated node signatures.
This is separate from source facts, parameter-default hints and runtime validation. It is an
opt-in annotation contract for the existing notebook path, not a DataFrame schema, general
project specification or functional-workflow type adapter. Default generation is unchanged.
Optional runtime class enforcement is described below; annotation-only output remains the default.

## Declaration

The input is a JSON object with exactly `schema_version`, `source_sha256` and `datasets`:

```json
{
  "schema_version": "1.0",
  "source_sha256": "<SHA-256 of the original notebook bytes>",
  "datasets": {
    "raw": "pandas.DataFrame",
    "model": "sklearn.pipeline.Pipeline",
    "fitted_model": "sklearn.pipeline.Pipeline"
  }
}
```

Replace the placeholder with the actual 64-character lowercase hexadecimal hash. The
[credit declaration](../../examples/nested_financial/credit_pipeline/node-types.contract.json)
supplies 28 explicitly authored types for its unchanged notebook. Its
[typed settings](../../examples/nested_financial/credit_pipeline/project-typed.json) compose
the declaration with existing regression/model-output settings; original settings and
historical experiment records are unchanged.

| Type string | Annotation meaning |
| --- | --- |
| `bool`, `int`, `float`, `str` | Corresponding Python scalar type. |
| `pandas.DataFrame`, `pandas.Series` | Pandas object class, without columns or dtypes. |
| `numpy.ndarray` | Array class, without dtype, shape or dimensions. |
| `sklearn.pipeline.Pipeline` | Pipeline object, without fitted-state or component guarantees. |
| `sklearn.base.BaseEstimator` | Broad estimator base class, without an exact concrete model type. |

No arbitrary Python expressions, user imports, unions, generic containers, `Any` declaration,
custom classes or runtime hooks are accepted. Omit an unknown type to retain an explicit gap.
The file is bounded to 64 KiB and 1-256 dataset entries. Duplicate keys, extra/missing fields,
unsupported versions/types and nonportable names fail. Dataset identifiers contain ASCII
letters/digits/underscores, start with a letter/underscore and are at most 256 characters.
The immutable Python `NotebookTypeContract` enforces the same rules and canonical ordering.
Its compact canonical JSON is also limited to 64 KiB; file loading additionally bounds the
actual bytes read, including whitespace.

## Bindings and generation

Review dataset identities in the ordinary generated `pipeline.py` or project preview. Use
the exact Kedro dataset key rather than a callable name or an ambiguous source symbol.
When a notebook rewrites `df`, the backend may produce `df__<source_task_name>`; the earlier
`df` and that new dataset can have different declarations. A declaration is applied to the
producer's corresponding return slot and every consuming argument bound to that dataset.
Profile prefixes/pipeline names do not change those bindings. Parameters retain their
separate provisional default-value hints.

Planning/generation requires original source facts and the usual source audit. A mismatched
notebook hash or unknown/unreferenced dataset blocks before publication. Local operations
re-read source and declarations for every plan/generate request; a preview is not an apply or
execution approval token. Direct Python callers must supply trusted source facts, as for
the other source-accounted generation APIs; this contract does not authenticate fabricated facts.

The shared renderer adds only fixed runtime imports for selected types and quoted annotations.
Private aliases avoid source/profile identifiers, including names such as `_ntk_pandas`.
No ML library is imported during analysis/generation. The generated project uses its existing
pandas/scikit-learn dependencies; the engine still depends only on nbformat. Business body ASTs,
assertions, parameter substitutions, return order and original functional source stay intact.
Strict provider contracts and the lower-level V1 reference renderer remain unchanged.

## Use from the interface, CLI or API

In VS Code, select the typed settings JSON, then use Preview Generated Files. Existing
configuration selection and preview commands require no new transformation rules in the UI.
For another notebook, add a root-contained `node_types` path to its local JSON settings.
The option is notebook-only. Inspect Source still inspects source alone; Preview/Generate
load and bind the declarations.

```bash
notebook-to-kedro project plan examples/nested_financial/credit_pipeline/project-typed.json
notebook-to-kedro project generate examples/nested_financial/credit_pipeline/project-typed.json generated/credit_typed
notebook-to-kedro generate examples/nested_financial/credit_pipeline/workflow.ipynb generated/credit_typed_cli --node-types examples/nested_financial/credit_pipeline/node-types.contract.json
```

For Python, use `load_notebook_type_contract(path)` and pass its immutable result as
`node_types=` to `generate_kedro_project`, together with original `source_facts=`. The shared
`render_kedro_project` preview API accepts the same option. The standalone `plan` text command
does not accept this option; use `project plan` for the actual annotated file preview.

## Evidence and limitations

The generated `node-types.json` is a report, not an input declaration or runtime certificate.
It records the canonical declaration, task/dataset bindings and sorted `untyped_datasets`.
Partially declared tuple outputs retain their ordered declared/`Any` slots. Docstrings distinguish
explicit types from unresolved types and parameter-default hints.

`runtime_type_validation` remains `not_run`; `dataframe_schema_validation` is `not_supported`.
Generation never runs source/tests, checks actual values or coerces data. Annotation-only mode
does not reject semantically wrong but structurally valid declarations: an integer computation
can be declared as `str`. Users must review declarations and validate values independently.
Generated regression/model-reload tests retain their supplied oracles/gaps. Running them does
not rewrite generation-time status. Strict generated-project type checking, rich DataFrame/array
schemas, custom model types and business-value validation remain future work.

## Optional runtime class enforcement

Set `enforce_node_types: true` alongside `node_types` in notebook project settings, or pass
`enforce_node_types=True` to the notebook generator. The flag must be a real boolean and
requires an explicit source-bound contract. The input contract schema remains unchanged.
The [checked credit settings](../../examples/nested_financial/credit_pipeline/project-checked.json)
reuse the same 28 authored declarations. The VS Code setup wizard does not author this option;
select that settings file and preview the generated decorator/helper/report.

```bash
notebook-to-kedro project plan examples/nested_financial/credit_pipeline/project-checked.json
notebook-to-kedro generate examples/nested_financial/credit_pipeline/workflow.ipynb generated/credit_checked --node-types examples/nested_financial/credit_pipeline/node-types.contract.json --enforce-node-types
```

This prepares checks without executing the notebook. When generated callables later run,
decorators validate declared business inputs before the source call and declared return slots
before handing results to Kedro. Only nodes with at least one declared boundary are wrapped;
undeclared datasets and parameter-default hints gain no checks. A single output is checked
as one value. Multiple outputs retain their ordered tuple; when any output is declared, an
incompatible return tuple/arity is also refused. All-undeclared outputs retain ordinary behavior.

| Policy | Runtime behavior |
| --- | --- |
| Python `bool`, `int`, `float`, `str` | Exact builtin class; reject subclasses, NumPy scalars and numeric widening such as `int` for `float`. No coercion. |
| DataFrame, Series, ndarray, Pipeline, BaseEstimator | `isinstance`; compatible subclasses are allowed. No shape, dtype, column, content or fitted-state inspection. |
| Input class mismatch | Builtin `TypeError`, prefix `NTV001`, with source task, dataset, expected type and observed class. Source business code has not run. |
| Output class/tuple mismatch | Builtin `TypeError`, prefix `NTV002`, after the source call and before returning to Kedro/catalog publication. Source side effects are not rolled back. |

The generated stdlib-only `_node_type_validation.py` is packaged with the project. Fixed
class references use the existing selected runtime imports; the converter is not imported by
the generated helper. It preserves callable names/signatures/docstrings, source body ASTs,
return object identity and original exceptions. It introduces no extra data copy, serializer,
pipeline ordering policy, import during analysis or engine dependency. Lower-level provider
contracts and `render_node_function` remain unchanged.

Checks use explicit exceptions and remain active under Python `-O`. Original notebook asserts
remain original instructions and can still be disabled by `-O`; this feature does not replace
them or provide business validation. An unfitted Pipeline or wrong-column DataFrame can pass
its class check. The wrappers are not an execution sandbox or immutable security policy;
generated code can be edited and `__wrapped__` exposes the original function.

The report adds `runtime_checks` with implementation `node-types-runtime-v1`, scalar/object
policies and `checked_tasks`. This records prepared enforcement, not passing execution evidence.
`runtime_type_validation` stays `not_run` even after an external run; evidence must be collected
separately. Default and annotation-only generation remain byte-compatible. See
[ADR 0029](../decisions/0029-runtime-notebook-type-checks.md).
