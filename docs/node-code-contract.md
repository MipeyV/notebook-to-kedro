# Node Code Contract

## Scope

`notebook_to_kedro.generation.code` defines the first provider-neutral code-generation boundary.
One request describes one task from a validated conversion plan, including a plan assembled by
the hybrid structureur. A provider proposes a Python function; the application parses and
validates it before returning a reviewable result. This API performs no code execution, imports
of proposed modules, or project writes. The existing deterministic generator remains the CLI's
generation path. Ollama code generation will be a separate adapter.

Both request and response use schema version `1.0`. Fixtures live in
`tests/fixtures/generation/code/v1/`. Breaking contract changes require a new version.

## Request

`build_node_code_request(plan, task_id, request_id=...)` validates the plan and copies the task's
source and interface. The caller supplies a correlation ID for the invocation.

| Field | Meaning |
| --- | --- |
| `schema_version`, `request_id`, `task_id` | Version and correlation identity. |
| `node_name` | Exact public ASCII function name. |
| `raw_source` | Original source assigned to the task, before parameter substitution. |
| `source_cell_ids`, `statement_ids` | Ordered source provenance from the plan. |
| `inputs`, `outputs` | Ordered Python variable names, not versioned catalog dataset names. |
| `parameter_names` | Kedro parameter keys referenced by the task. |
| `parameter_arguments` | Corresponding function argument names from the plan. |
| `allowed_imports` | Import statements from the plan available to the provider. |

The required function signature is `inputs + parameter_arguments`, with no defaults, variadic,
positional-only or keyword-only arguments. Parameter values remain in Kedro configuration; code
must consume their function arguments. Requests reject invalid identifiers and argument collisions.

## Response And Provider

`NodeCodeProvider.complete(request)` returns raw JSON. `NodeCodeResponse` requires exactly:

- `schema_version`, `request_id` and `task_id`;
- `function_code`, containing one synchronous function definition;
- `imports`, containing the required subset of allowed import statements;
- `review_notes`, containing review observations, possibly empty.

`NODE_CODE_RESPONSE_JSON_SCHEMA` describes the structured output for future adapters. The JSON
decoder rejects missing or unknown fields, duplicate object keys, incorrect field types, duplicate
array entries, and unsupported versions. Parsing alone does not validate the Python code.

`FakeNodeCodeProvider` records invocations and returns a fixed response or raises a configured
error, enabling offline tests without a model. `request_node_code` parses and validates the
response, then returns `NodeCodeResult` with the original request and provider/model identity
captured by the application. Parse and validation errors raise `ValueError`; provider failures
propagate. No automatic retry or fallback is introduced at this boundary.

## Static Validation

`validate_node_code` checks:

1. Request and task identity.
2. Imports matching the allowed statements by AST, including aliases; relative imports, wildcard
   imports, import binding collisions, and additional statements are rejected.
3. Exactly one synchronous function with the requested name and signature, with no module-level
   executable statements in `function_code`.
4. No decorators, annotations, generic type parameters, nested functions/classes/lambdas, local
   imports, `global`, `nonlocal`, or generator yields in this initial subset.
5. Exactly one terminal return: `None` (or bare `return`) for no outputs, the variable for one
   output, or the ordered tuple of variables for multiple outputs.
6. Successful compilation without execution, and no unknown global references according to
   Python's symbol table, including comprehension scopes. Declared imports and Python builtins
   are available; notebook globals must be passed as inputs.

These checks establish structural compatibility only. They do not prove that every local variable
is assigned on every execution path, that parameters are used correctly, that computations match
the original notebook, or that imported packages are installed. A structurally valid function
can still perform I/O or produce incorrect results. This validator is not an execution sandbox.
Behavioral equivalence, isolated execution and review are subsequent stages before generated
proposals can be included in a project.

## Offline Example

```python
from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.generation.code import (
    FakeNodeCodeProvider,
    NodeCodeResponse,
    build_node_code_request,
    request_node_code,
)

plan = plan_notebook_path("tests/fixtures/notebooks/simple_training.ipynb")
request = build_node_code_request(plan, "task-0009", request_id="code-predict-1")
response = NodeCodeResponse(
    schema_version="1.0",
    request_id=request.request_id,
    task_id=request.task_id,
    function_code=(
        "def predict(model, X_test):\n"
        "    predictions = model.predict(X_test)\n"
        "    return predictions\n"
    ),
)
result = request_node_code(request, FakeNodeCodeProvider(response_json=response.to_json()))
```

The result is a proposal ready for further review. This example does not run the function or
alter a generated project.
