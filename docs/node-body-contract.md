# Node Body Contract

## Scope

`NodeBodyResponse` is a separate versioned response format for proposing only a node's body.
It reuses the immutable `NodeCodeRequest`: source cells, statement IDs, original source,
ordered inputs and outputs, parameter arguments and allowed imports remain trusted evidence.

This step implements an offline Python API, not an Ollama mode, CLI command, benchmark adapter
or automatic project writer. Existing full-code providers, prompts `v1`/`v4`, contracts and
validator `node-code-validation-v4` are unchanged. No new model-accuracy result is claimed.

## Response

`NODE_BODY_SCHEMA_VERSION` is `1.0`, independently versioned from the full-code contract.
`NODE_BODY_RESPONSE_JSON_SCHEMA` describes exactly these required JSON fields:

```json
{
  "schema_version": "1.0",
  "request_id": "body-1",
  "task_id": "task-1",
  "body_code": "scaled = values\nscaled",
  "review_notes": []
}
```

Parsing rejects extra, missing or duplicate fields, wrong types, unsupported versions,
empty identities or body text, and duplicate or empty review notes. The Python dataclass
is immutable. Nonempty text is not necessarily valid code; assembly performs static checks.
`imports` and `function_code` belong to the old response format and are forbidden here.

## Assembly

```python
from notebook_to_kedro.generation.code import (
    NodeBodyResponse,
    NodeCodeRequest,
    assemble_node_body,
)

request = NodeCodeRequest(
    schema_version="1.0",
    request_id="body-1",
    task_id="task-1",
    node_name="scale",
    raw_source="scaled = values\nscaled",
    source_cell_ids=("cell-1",),
    statement_ids=("cell-1-stmt-0", "cell-1-stmt-1"),
    inputs=("values",),
    outputs=("scaled",),
)
proposal = NodeBodyResponse(
    schema_version="1.0",
    request_id=request.request_id,
    task_id=request.task_id,
    body_code=request.raw_source,
)
response = assemble_node_body(request, proposal)
```

The returned `NodeCodeResponse` contains:

```python
def scale(values):
    scaled = values
    scaled
    return scaled
```

`NODE_BODY_ASSEMBLY_VERSION` is `node-body-assembly-v1`. Assembly:

1. Rejects mismatched request or task identities.
2. Parses the body and builds the exact function name and argument order from the request.
3. Appends `return None`, a single output, or the ordered output tuple.
4. Selects permitted import statements whose bindings are referenced globals, including
   comprehension scopes, in request order. Local variables and arguments do not select imports.
   Multi-name imports remain whole statements; unused permissions are omitted but still checked.
5. Runs the existing strict full-code validator before returning a response.

Assembly uses Python ASTs rather than textual indentation, preserving multiline string values.
Comments, quoting and formatting can normalize. Output is deterministic for the same inputs
on the same Python runtime; byte-identical formatting across Python versions is not guaranteed.
Review notes are carried through, not interpreted as approval or executed.

## Fidelity And Trust

The body must already contain only the exact planned parameter substitutions. Assembly does
not rewrite literals, restore omitted expressions, strip imports or returns, or repair code.
The validator rejects omitted, added, reordered or changed instructions; assertions must also
remain intact. Standalone notebook result expressions remain statements before the appended
return. Complete function wrappers, body imports, nested scopes, extra returns, unknown globals,
invalid import permissions and conflicting selected import bindings are rejected.

No proposed code is executed, no modules are imported from request permissions, no provider
is contacted and no files are written. Static acceptance is neither behavioral proof nor a
security sandbox: a faithful body can contain side effects already present in the notebook.
The existing behavioral API still requires `allow_untrusted_code_execution=True` and runs in
bounded subprocesses, not an OS sandbox. Project generation does not consume proposals automatically.

## Verification And Next Step

Offline regression tests cover exact fields, import selection, zero/one/multiple outputs,
parameter fidelity, standalone expressions, multiline strings, malformed proposals and
absence of execution. All eight manually reviewed `v2` reference bodies reconstruct the
reference function ASTs. With explicit test consent, their assembled responses match all
seventeen reviewed behavioral scenarios, including expected exceptions.

These are reference-compatibility tests, not outputs sampled from a model. The next step is a
separate opt-in body-only local provider and prompt, then a provenance-aware benchmark/replay
adapter recording the body schema, assembly version, exact body and assembled response.
Compare both local models on the unchanged corpus before considering promotion, and use fresh
independent tasks before claiming generalization. See the
[rejected statement-retention experiment](node-code-statement-retention.md) for motivation.
