# Node Code Contract

## Scope

`notebook_to_kedro.generation.code` defines the first provider-neutral code-generation boundary.
One request describes one task from a validated conversion plan, including a plan assembled by
the hybrid structureur. A provider proposes a Python function; the application parses and
validates it before returning a reviewable result. This API performs no code execution, imports
of proposed modules, or project writes. The existing deterministic generator remains the CLI's
generation path. An opt-in local Ollama adapter is available through this Python API.

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

`NODE_CODE_RESPONSE_JSON_SCHEMA` describes the structured output for adapters. The JSON
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
6. Assertion preservation: each top-level source statement containing an assertion must retain
   the same AST and statement index in the function. Conditions, messages, assertion ordering,
   and whole enclosing control-flow statements are compared. Added assertions are rejected too.
7. Successful compilation without execution, and no unknown global references according to
   Python's symbol table, including comprehension scopes. Declared imports and Python builtins
   are available; notebook globals must be passed as inputs.

These checks establish structural compatibility only. They do not prove that every local variable
is assigned on every execution path, that parameters are used correctly, that computations match
the original notebook, or that imported packages are installed. A structurally valid function
can still perform I/O or produce incorrect results. This validator is not an execution sandbox.
Behavioral equivalence, isolated execution and review are subsequent stages before generated
proposals can be included in a project.

`NODE_CODE_VALIDATOR_VERSION` identifies these rules (`node-code-validation-v2`). Assertion
comparison ignores comments and formatting but deliberately rejects any rewrite of an enclosing
statement containing an assertion, including potentially valid parameter substitutions in that
block. Until explicit transformation evidence is available, such cases require review. The check
does not prove that earlier assignments preserve the values being asserted or that unrelated
statements are faithful. Assertions being present does not make the proposal safe to execute.

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

## Local Ollama Proposals

`OllamaNodeCodeProvider` implements the same contract using the existing local Ollama chat
transport. It introduces no SDK dependency. Construction performs no network I/O; only an explicit
call sends the task source, provenance, interfaces, and allowed imports to the configured server.
It does not send the notebook's outputs or read datasets. Source code can still contain secrets;
review what you send, even to a local model.

With Ollama running and an already downloaded local model:

```python
from notebook_to_kedro.generation.code import OllamaNodeCodeProvider, request_node_code

provider = OllamaNodeCodeProvider(model_name="qwen3:8b", timeout_seconds=120)
result = request_node_code(request, provider)
proposal = result.response.function_code
```

The `request` above is the task request from the offline example. The model name is explicit;
this example is not an accuracy recommendation. There is no download, retry, cloud fallback, code
execution, or project write. Only local HTTP loopback URLs are accepted, cloud model tags are
rejected, and the transport uses a timeout and bounded response size (4 MiB by default). Keep
Ollama configured with `OLLAMA_NO_CLOUD=1` for a local-only deployment.

`render_node_code_prompt` is deterministic and versioned by `NODE_CODE_PROMPT_VERSION`
(`node-code-v1`). It supplies original task evidence and the exact signature and return order,
asks for faithful operations rather than repairs, and treats notebook contents as untrusted data.
The request uses the response JSON schema, non-streaming chat, temperature zero, and `think=false`.
These settings do not guarantee deterministic or correct model output.

The original prompt remains in use: two prompt-only experiments did not improve fidelity enough
to replace it; their results are recorded in the benchmark documentation. Assertion preservation
is enforced by the validator, not by trusting instructions to the model. Request and response
JSON schemas remain at version `1.0`; prompt and validator versions evolve independently.

`complete` returns raw assistant JSON; use `request_node_code` to parse and statically validate it.
Transport failures raise `NodeCodeProviderError` from `notebook_to_kedro.exceptions`, with stable
`code` and `message` fields inherited from the transport diagnostic. Invalid model JSON or code
raises `ValueError`; neither failure silently falls back to accepted code.

The request currently gives parameter names and function arguments, not an exact literal-to-
parameter substitution map. Ambiguities must be reviewed; parameter fidelity is not established
by the static validator. Tests use mocked HTTP responses and establish adapter behavior, not real
model accuracy. The [code benchmark](node-code-benchmark.md) records corpus-wide static acceptance,
V1 AST matches and missing parameter reads. Behavioral equivalence and isolated execution remain
separate milestones before proposals can be included in generated projects.
