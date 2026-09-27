# Exact Parameter Evidence

## Purpose

Parameter names alone do not identify which occurrence of a literal to replace, or whether the
argument contains a scalar, list or dictionary. In the earlier code-provider experiments,
proposals sometimes produced `drop(columns=[prepare_features_drop_columns])` or changed
`df["target"]` when only the `drop` argument should have changed.

`build_parameter_evidence(request)` now derives explicit substitutions using the same
`parameter_replacements` implementation as the deterministic V1 generator. It performs no model
calls, notebook execution, expression evaluation beyond `ast.literal_eval`, or file writes.
It is available from `notebook_to_kedro.generation.code` for other providers to reuse.

## Contract

Evidence envelope version `1.0` is identified by `NODE_CODE_PARAMETER_EVIDENCE_VERSION`.
Each immutable `ParameterReplacement` contains:

| Field | Meaning |
| --- | --- |
| `parameter_name` | Exact parameter key requested by the plan. |
| `function_argument` | Exact corresponding argument from the request, not a guessed identifier. |
| `source_expression` | Complete original expression being replaced. |
| `value_type` | Python type name of that literal, e.g. `list`, `dict`, `str`, `bool`, `int`, `float`, `tuple`. |
| `start_offset`, `end_offset` | Zero-based, half-open character range within the request's `raw_source`. |

Offsets count Python string characters, not UTF-8 bytes and not positions in the entire notebook.
Cell and statement provenance remain in the request. Multiline expressions, CRLF line endings
and non-ASCII source characters are supported. AST byte columns are converted before slicing.
The evidence's `value_type` describes the original literal, not a runtime validation of user-
overridden configuration values or a dataset column's type.

For example, given:

```python
X = df.drop(columns=["target"])
y = df["target"]
```

the substitution covers the complete `["target"]` expression inside the `drop` call and has
`value_type="list"`. The intended result is:

```python
X = df.drop(columns=prepare_features_drop_columns)
y = df["target"]
```

The surrounding list must not be retained, and the second occurrence of `"target"` must not be
changed. Offsets are calculated by syntax and the supported call role, not by global text search.
Multiple substitutions are sorted by source position. Consumers editing source text must apply
them in reverse order to preserve the original offsets.

## Supported Scope

Evidence supports the V1 extraction rules: selected `RandomForestClassifier`, `StandardScaler`
and `train_test_split` keyword arguments, `drop(columns=...)`, and positional or keyword
`fillna` values. It is not a general interpreter of arbitrary Python calls or a new set of
supported notebook operations.

The node-code evidence builder requires exactly one recognized literal expression per requested
parameter. Missing sites, repeated candidates, ambiguous parameter suffixes and nonliteral
expressions are rejected before the opted-in adapter's HTTP call. Empty parameter lists yield empty
evidence. Arbitrary manually constructed requests can still satisfy the JSON schema while falling
outside this evidence subset; construction then raises `ValueError` (or `SyntaxError`
for malformed source) instead of asking the model to invent a mapping.

## Provider Integration

The default prompt remains `node-code-v1`. Explicitly enabling `include_parameter_evidence=True`
on `OllamaNodeCodeProvider` or `render_node_code_prompt` selects experimental `node-code-v4`,
identified by `NODE_CODE_PARAMETER_PROMPT_VERSION`. It includes the versioned substitutions as a
separate JSON block alongside the unchanged original task evidence. It instructs the provider to
replace the entire indicated expression with the bare argument name and leave other occurrences
alone. This option supplements the original prompt; the rejected prompts v2/v3 are not enabled.

```python
from notebook_to_kedro.generation.code import OllamaNodeCodeProvider, build_parameter_evidence

substitutions = build_parameter_evidence(request)
provider = OllamaNodeCodeProvider("qwen3:8b", include_parameter_evidence=True)
# When benchmarking, pass prompt_version=provider.prompt_version.
```

Here `request` is a `NodeCodeRequest`, for example from the node-code contract documentation.
The provider's read-only `prompt_version` reports the selected mode for benchmark provenance.
The option is not the default because the first measured corpus run did not improve overall
acceptance or AST matching. Default adapter calls preserve the previous prompt and behavior.

Request and response JSON schemas remain at `1.0`: no new serialized request field is required,
and existing fixtures and fake providers remain compatible. Derived evidence is available to
all providers through the Python helper rather than stored as an independently editable copy of
source facts. The benchmark retains source requests and records the prompt version; evidence
can be recomputed using the corresponding code revision.

The validator remains `node-code-validation-v2`. It still checks structure and assertion blocks,
not exact parameter-substitution semantics. A model can ignore this evidence or introduce other
changes; AST comparison and subsequent behavioral validation remain necessary. The application
does not patch or execute a proposed function automatically.
