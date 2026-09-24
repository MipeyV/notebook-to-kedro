# Local Ollama Provider

## Scope

`OllamaSemanticPlanningProvider` connects the semantic planning boundary to a local Ollama
server through Python's standard-library HTTP client. The core package does not depend on the
Ollama SDK.

The adapter uses Ollama's native chat endpoint:

```text
POST http://localhost:11434/api/chat
```

It sends one user message, disables streaming and model thinking, sets temperature to zero, and
supplies the semantic response JSON Schema through Ollama's `format` field. Disabling thinking
keeps this constrained extraction task focused and avoids paying inference latency for a hidden
reasoning trace. The adapter extracts the raw structured response from `message.content`; the
existing orchestration layer then parses and validates it.

Official references:

- [Ollama API introduction](https://docs.ollama.com/api/introduction)
- [Chat endpoint](https://docs.ollama.com/api/chat)
- [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Thinking controls](https://docs.ollama.com/capabilities/thinking)
- [API errors](https://docs.ollama.com/api/errors)

## Safety Boundary

The adapter accepts only unencrypted loopback URLs using `localhost`, `127.0.0.1`, or `::1`.
Paths, credentials, query strings, fragments, HTTPS URLs, and non-local hosts are rejected. Known
Ollama cloud model tags such as `:cloud` and `*-cloud` are also rejected.

Ollama itself supports cloud inference through its local server, so client-side name checks are
not a complete isolation boundary. For enforced local-only operation, disable Ollama cloud
features with `OLLAMA_NO_CLOUD=1` or `disable_ollama_cloud: true` in Ollama's server configuration,
restart Ollama, and select a downloaded model. See the
[Ollama FAQ](https://docs.ollama.com/faq#how-can-i-disable-ollama-cloud-features).

The local Ollama API does not require authentication. Remote and cloud providers require a
separate adapter with explicit user consent and credential handling.

Responses are bounded to 4 MiB by default. Connection failures, timeouts, HTTP errors, malformed
Ollama envelopes, generation errors, and oversized responses are normalized as
`SemanticProviderError`. Expected provider errors trigger the deterministic V1 fallback in
`request_semantic_planning`.

## Python Usage

```python
from notebook_to_kedro import PlannerMode, plan_notebook_path

plan = plan_notebook_path(
    "notebooks/model.ipynb",
    planner=PlannerMode.HYBRID,
    ollama_model="your-local-model",
    ollama_timeout_seconds=120,
)
```

Applications that manage planner instances separately can call `create_semantic_planner` or build
`OllamaSemanticPlanningProvider` and `HybridSemanticPlanner` directly. The high-level API and CLI
assemble accepted suggestions into a validated `ConversionPlan`; expected provider or response
failures return a diagnostic-bearing deterministic fallback.

## Local Setup

Ollama and a model are not required for installation, unit tests, or CI. They are needed only for
an opt-in local inference test:

1. Install Ollama using its official platform instructions.
2. Disable Ollama cloud features when notebook data must remain strictly local.
3. Download a model supported by the available machine.
4. Confirm the local server is available on port `11434`.
5. Select `hybrid` in the Python API or CLI and pass that model name.

Model selection and live quality evaluation remain separate work. No external LLM test runs in
the default test suite.
