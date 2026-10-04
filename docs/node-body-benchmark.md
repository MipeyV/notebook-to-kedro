# Body-Only Benchmark And Replay

## Scope

The Python API now benchmarks body-only providers on the independent node-code and behavioral
corpora, preserving rejected proposals rather than reporting only successful nodes. It uses the
same static validator, consent-gated subprocess execution, comparators and metric denominators
as the full-code benchmark. Full-code artifacts and CLI commands are unchanged.

This step adds an API and a separate artifact envelope, not a body-only CLI or live model
measurement. Offline tests and approved-reference execution are compatibility checks, not
evidence that a model has improved.

## Run And Archive

```python
from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    BehavioralExecutionConfig,
    behavioral_code_benchmark_to_dict,
    collect_environment_provenance,
    create_node_body_benchmark_artifact,
    load_behavioral_corpus,
    load_node_code_corpus,
    run_node_body_benchmark,
    write_node_body_benchmark_artifact,
)
from notebook_to_kedro.generation.code import OllamaNodeBodyProvider

behaviors = load_behavioral_corpus("tests/fixtures/evaluation/behavioral/v2")
nodes = load_node_code_corpus("tests/fixtures/evaluation/node_code/v2")
base_url = "http://localhost:11434"
model = "your-downloaded-model"
execution = BehavioralExecutionConfig(timeout_seconds=10)
provider = OllamaNodeBodyProvider(model, base_url=base_url, timeout_seconds=120)
report = run_node_body_benchmark(
    behaviors,
    nodes,
    provider,
    project_root=".",
    execution_config=execution,
    allow_untrusted_code_execution=True,
)
summary = behavioral_code_benchmark_to_dict(report.benchmark)["summary"]
configuration = BehavioralBenchmarkConfiguration(
    base_url, 120, include_parameter_evidence=True, execution=execution
)
provenance = collect_environment_provenance(
    project_root=".", ollama_base_url=base_url, model_name=model
)
artifact = create_node_body_benchmark_artifact(report, provenance, configuration)
write_node_body_benchmark_artifact("generated/new-body-run.json", artifact)
```

Use a controlled environment, an already downloaded local model and a fresh output path.
Construction and serialization do not call a provider; `run_node_body_benchmark` does.
Provenance collection with Ollama settings explicitly queries local model/runtime metadata.
Configuration is caller-supplied and must describe the actual run. Metadata may be null when
capturing a non-Ollama provider; the approved-reference tests use an explicitly offline provider.

Consent must be the boolean `True`, not a truthy replacement. Corpus validation, source hash
verification, approved-reference static validation and parameter evidence preflight occur before
any provider call. Each node is requested once, then accepted assemblies run on their linked
scenarios. Unexpected provider implementation errors propagate instead of being hidden as model
failures.

## Evidence And Metrics

`NodeBodyBenchmarkReport` retains a behavioral `benchmark`, an ordered `body_responses` tuple and
a `corpus_sha256`. Each benchmark proposal preserves:

- exact raw assistant JSON, including its original whitespace, when any was received;
- a parsed body when the body-response contract is valid;
- an assembled full-code response only when assembly and static validation succeeded;
- provider errors, invalid response contracts and invalid bodies as distinct statuses;
- diagnostics, proposal duration and behavioral evaluations for accepted proposals only.

Rejected bodies are not repaired and never reach execution. Their missing assembled response is
explicitly null, not a synthetic replacement. Provider errors have no invented model response.
The summary retains separate node acceptance, evaluated-match and end-to-end scenario rates,
including not-evaluated scenarios in the full denominator. Timing named `provider_duration_seconds`
follows the existing benchmark convention: the timed proposal phase includes provider/prompt work,
JSON parsing, assembly and static validation, not just model inference.

`NodeBodyBenchmarkArtifact` schema `1.0` is tagged `artifact_kind: "node-body"`. Its envelope stores
body schema, assembly and parameter-evidence versions, corpus identity, parsed bodies by case ID
and an embedded behavioral artifact carrying raw responses, metrics, prompt/validator versions,
execution policy, configuration, environment provenance and canonical report hash.

The whole envelope has its own canonical SHA-256 identity. It is intentionally incompatible with
the full-code artifact loader: use the body-specific APIs and do not replay the embedded artifact
through the full-code API. Duplicate JSON keys and unsupported envelope fields or versions are
rejected. Parsed bodies must match raw responses, accepted cached responses must match assembly,
and rejected records cannot contain assembled code or evaluations. Reading does not execute code.
The frozen dataclasses contain dictionaries; writing and replay therefore revalidate their contents
and hashes. Hashes detect accidental changes, not authorship or maliciously recomputed evidence.

## Offline Replay

```python
from notebook_to_kedro.evaluation import (
    load_node_body_benchmark_artifact,
    node_body_benchmark_artifact_sha256,
    replay_node_body_benchmark,
)

source = load_node_body_benchmark_artifact("generated/new-body-run.json")
replayed = replay_node_body_benchmark(
    source,
    behaviors,
    nodes,
    project_root=".",
    allow_untrusted_code_execution=True,
)
replay_artifact = create_node_body_benchmark_artifact(
    replayed,
    collect_environment_provenance(project_root="."),
    source.benchmark.configuration,
    mode="replay",
    source_artifact_sha256=node_body_benchmark_artifact_sha256(source),
)
write_node_body_benchmark_artifact("generated/new-body-replay.json", replay_artifact)
```

Replay serves the recorded raw bodies and transport failures without Ollama. It parses and
assembles bodies again, applies current supported static validation, and only then executes
accepted proposals with renewed consent. It does not execute cached full-code responses or reuse
cached behavioral outcomes. Provider/proposal time is zero and cannot be compared with a live run
as model latency.

The complete corpus identity covers requests, approved references, negative controls, behavioral
inputs, expected results and comparators. Case order can change, but corpus content, recorded
requests, notebook paths, source hashes and scenario count must agree. The assembly, body schema,
evidence and validator versions must be compatible; use the original Python runtime if AST
formatting changes prevent exact cached-assembly verification. Execution configuration defaults
to the source artifact and may be explicitly overridden for the replay.

The atomic writer reuses exclusive publication and refuses to overwrite an existing output.
Keep artifacts private in ignored `generated/`; raw notebook content may be sensitive.

## Verification And Next Step

Offline tests cover all failure stages, raw/parsed consistency, provenance versions, corpus
binding, file handling, mutation detection and network-free replay. An integration test requests
the eight reviewed reference bodies once, executes all seventeen scenarios, writes and reloads an
artifact, then replays all seventeen through real subprocesses. All match their approved
expectations; these are reference results, not live model outputs.

Next: add explicit CLI run/replay and comparison for this envelope, including full-code versus
body-only comparisons with compatible corpus identities and clearly labeled latency. Then run
both local models on the unchanged corpus before claiming any improvement. Subprocess containment
is not an OS security sandbox and no proposal automatically enters project generation.
