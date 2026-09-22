# Semantic Planning Contract

## Purpose

The semantic planning contract is the provider-neutral boundary between deterministic V1
analysis and future local or remote LLM adapters. A provider receives immutable notebook facts
and a deterministic baseline plan, then returns structured suggestions. It never writes a Kedro
project and it does not replace static validation.

The current contract version is `1.0`.

## Request

`SemanticPlanningRequest` contains:

| Field | Owner | Meaning |
| --- | --- | --- |
| `schema_version` | application | Contract version expected by both sides. |
| `request_id` | application | Stable correlation ID for one invocation. |
| `prompt_version` | application | Version of the prompt and instructions. |
| `notebook_facts` | V1 analyzer | Canonical cells, statements, symbols, dependencies, source, and diagnostics. |
| `baseline_plan` | V1 planner | Deterministic task boundaries and the allowed datasets, parameters, and diagnostics. |

The baseline is projected into JSON instead of exposing a second mutable plan format. Notebook
source already exists in `notebook_facts`, so it is not duplicated inside each baseline task.

## Response

`SemanticPlanningResponse` contains a request ID, review notes, and ordered task suggestions.
Each `SemanticTaskSuggestion` must provide:

- source cell and statement IDs;
- a public ASCII Python node name;
- input, output, and parameter references;
- a pipeline ID;
- optional review notes.

The exported `SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA` can be passed to providers that support
structured JSON output. Parsing is strict: required fields cannot be omitted and unknown fields
are rejected.

## Trust Boundary

Provider and model names are not model-generated fields. The application records them in
`SemanticPlanningTrace`, then combines the request, response, and trace in an auditable
`SemanticPlanningResult`.

`validate_semantic_planning_response` rejects a response when it:

- targets another request;
- references an unknown cell or statement;
- assigns a statement to the wrong cell or to multiple nodes;
- omits or invents a baseline statement;
- invents an input, output, or parameter;
- attaches a known parameter to the wrong source cells.

Passing this validation only establishes structural compatibility with V1 evidence. It does not
yet approve generated node code or prove behavioral equivalence. Those remain separate review
and execution stages.

## Provider Orchestration

`SemanticPlanningProvider` is the narrow transport boundary. It receives a
`SemanticProviderRequest` containing:

- the request ID;
- a deterministic `planning-v1` prompt;
- the structured-output response schema.

The provider returns raw JSON. It does not parse, validate, or merge its own output. The
orchestrator owns those steps and records provider and model identity independently.

`FakeSemanticPlanningProvider` supports offline tests with either fixed JSON or a fixed
`SemanticProviderError`. It performs no network or filesystem I/O and records each request for
assertions.

`request_semantic_planning` returns a `SemanticPlanningOutcome`:

- a valid, statically compatible response produces an auditable `SemanticPlanningResult`;
- an expected provider error or invalid response produces a `SemanticPlanningFailure` and exposes
  the deterministic baseline plan as `fallback_plan`;
- unsupported prompt versions and unexpected programming errors remain visible instead of being
  silently converted into fallback.

An accepted result is still a suggestion, not a generation-ready `ConversionPlan`. A later hybrid
assembly step must assign deterministic IDs, merge the suggestion with static plan data, and run
the existing conversion-plan validator before generation.

## Compatibility

Additive or breaking response changes require an explicit schema decision. A breaking change
must introduce a new version rather than silently accepting a different payload under `1.0`.
Versioned valid and invalid examples live under:

```text
tests/fixtures/semantic/planning/v1/
```

The local Ollama implementation is documented in
[`ollama-provider.md`](ollama-provider.md). The next semantic step is to convert accepted
suggestions into a deterministic, fully validated `ConversionPlan` without weakening V1
provenance.
