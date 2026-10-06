# Local Body-Only Node Provider

## Scope

`OllamaNodeBodyProvider` explicitly requests a `NodeBodyResponse` rather than a complete function.
It does not replace `OllamaNodeCodeProvider`, the deterministic converter or CLI defaults.
Prompt `node-body-v1` is separate from the unchanged full-code prompts `node-code-v1`/`node-code-v4`.

The provider reuses the existing standard-library Ollama chat transport and its loopback URL,
local-model tag, timeout and response-size checks. It sends the body JSON schema, with streaming
and thinking disabled and temperature zero. Construction does not call Ollama, download a model,
execute code or write a project. There is no retry or automatic fallback to another model.

## Python API

Use an already downloaded local model and a running local Ollama server:

```python
from pathlib import Path

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.generation.code import (
    OllamaNodeBodyProvider,
    build_node_code_request,
    request_node_body,
)

plan = plan_notebook_path(Path("tests/fixtures/notebooks/simple_training.ipynb"))
task = plan.task_candidates[1]
request = build_node_code_request(plan, task.id, request_id="body-prepare")
provider = OllamaNodeBodyProvider("your-downloaded-model", timeout_seconds=120)
result = request_node_body(request, provider)

body = result.body_response.body_code
function = result.response.function_code
imports = result.response.imports
raw_json = result.raw_response_json
```

The request contains original source, source provenance, the trusted interface and import
permissions. The prompt always supplies exact, independently derived parameter evidence,
including an empty substitutions array for parameter-free tasks. Ambiguous mappings fail before
model I/O; there is no switch to weaken this mode to a prompt without parameter evidence.

`body_code` must contain top-level body statements, with only original internal indentation.
The model must not provide a signature, imports or return. It must retain standalone expressions,
assertions and statement order without adding source-absent output expressions. Source and
instruction-like comments remain untrusted JSON data. Review notes cannot waive validation.

## Service And Provenance

`NodeBodyProvider` is the provider-neutral protocol: `provider_name`, `model_name`, `prompt_version`
and `complete(request) -> str`. Direct `complete` returns untrusted assistant JSON. Use
`request_node_body` to preflight parameters, parse the strict body contract, assemble the trusted
function shell and run the existing validator before accepting a result.

The immutable `NodeBodyResult` retains the request, parsed `body_response`, assembled full-code
`response`, exact `raw_response_json`, provider/model names, prompt version and assembly version.
Raw JSON preserves original whitespace rather than being reconstructed from the parsed object.
This provenance belongs to the application, not fields claimed by the model.

`NodeCodeProviderError` retains existing Ollama error codes. JSON and static validation failures
raise `ValueError`; no malformed body is repaired. Full-code responses are rejected by the body
service and body responses are rejected by the full-code service. The result does not bypass
execution consent or automatically enter generated projects.

## Verification And Limitations

Offline tests inject transport responses; no live model is called. They cover exact HTTP payloads,
prompt evidence and a pinned digest, local configuration, bounded failure behavior, incompatible
formats, provenance, preflight failures, invalid bodies and absence of execution. All eight
approved `v2` reference bodies pass through the simulated provider/service path. This verifies
integration, not model accuracy or improved acceptance. Prior full-code measurements remain
historical full-code results and must not be attributed to this new mode.

The [body-only benchmark/replay API](node-body-benchmark.md) now preserves raw body responses,
assembly/schema/prompt versions, accepted assembled responses and rejected proposals in a separate
artifact envelope. The CLI now explicitly selects this mode with `--proposal-format node-body`
for run/replay/compare. Body comparisons require matching corpus/source and execution contracts;
live accuracy measurements of both local models on the unchanged corpus remain next.
Keep behavioral execution opt-in: subprocesses provide fault containment,
not an OS security sandbox. See the [body contract](node-body-contract.md),
[local transport](ollama-provider.md) and [full-code API](node-code-contract.md).
