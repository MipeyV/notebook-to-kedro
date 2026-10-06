# Body-Only Benchmark And Replay

## Scope

The Python API now benchmarks body-only providers on the independent node-code and behavioral
corpora, preserving rejected proposals rather than reporting only successful nodes. It uses the
same static validator, consent-gated subprocess execution, comparators and metric denominators
as the full-code benchmark. Full-code artifact formats and CLI defaults are unchanged.

The Python API and CLI explicitly select a separate body-only artifact envelope. Offline tests
and approved-reference execution are compatibility checks, not evidence that a model has improved.
No body-only live model measurement has been recorded yet.

## CLI

Use `--proposal-format node-body` on each action. Without it, `full-code` remains the default;
the loaders reject the other format rather than guessing or silently converting it.

```bash
uv run notebook-to-kedro behavioral-benchmark run tests/fixtures/evaluation/behavioral/v2 tests/fixtures/evaluation/node_code/v2 generated/body-run.json --proposal-format node-body --ollama-model qwen3:8b --ollama-timeout 120 --allow-untrusted-code-execution
uv run notebook-to-kedro behavioral-benchmark replay generated/body-run.json tests/fixtures/evaluation/behavioral/v2 tests/fixtures/evaluation/node_code/v2 generated/body-replay.json --proposal-format node-body --allow-untrusted-code-execution
uv run notebook-to-kedro behavioral-benchmark compare generated/body-run.json generated/body-replay.json --proposal-format node-body --output generated/body-comparison.json
```

`run` always includes exact parameter evidence in body mode; `--include-parameter-evidence`
is redundant there. Ollama is required only for `run`. Both run and replay require explicit
execution consent. `--project-root` resolves the reviewed source paths. `--execution-timeout`
defaults to ten seconds on both actions; replay preserves the source byte/capture limits.
To compare a run made with a non-default execution timeout to its replay, pass that same
timeout to replay. Every output path must be new, including comparison files. Omitting
`--output` on compare prints JSON to stdout. Expected failures return exit code 1 on stderr;
invalid CLI options return argparse's exit code 2.

## Comparison

`compare_node_body_benchmark_artifacts(baseline, candidate)` and the CLI compare two **body-only**
artifacts. They revalidate both envelopes, raw/parsed/assembled consistency and report hashes
before inspecting results. They require identical corpus digests, node case IDs, recorded requests,
source paths/hashes, scenario counts, validator versions, execution policies and execution settings.
Model and prompt identities may differ: these are the experimental variables, not silently merged
identities. Metadata includes both configurations and environment/model provenance.

Comparison schema `1.0` is tagged `node-body-comparison` and identifies the **whole outer artifacts**.
It contains acceptance and end-to-end match rate deltas, proposal/scenario status changes, regression
counts, per-node rejection diagnostics and both full summaries. Summaries retain every rejection,
not-evaluated count and the complete scenario denominator. The scenario-change table uses the union
of evaluated scenario IDs; scenarios never evaluated on either side remain in summary denominators,
not invented rows. A missing evaluated outcome is labeled `not_evaluated`.

Provider timing means the whole proposal phase (prompt/provider, parse, assembly and validation),
not pure inference latency. Its delta is populated only for two live runs; replay comparisons mark
it non-comparable and emit a null delta. Live timings are observations under the recorded environment,
not evidence of equivalent hardware, model residency or request settings. Execution timing remains
an observed subprocess duration, not model latency. Comparison only reads evidence: it neither
executes code nor contacts Ollama.

Mixed full-code/body-only comparisons are intentionally rejected. Legacy full-code artifacts do
not record the complete corpus digest; matching case names alone cannot establish identical inputs,
references and comparators. A future corpus-bound bridge is needed before automating cross-format
comparisons. Neither artifact format nor the existing full-code comparator is changed here.

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

Next: run both local models on the unchanged corpus with this explicit body mode, archive their
responses, replay them offline and compare repeated runs before claiming any improvement. Add a
corpus-bound full-code/body-only comparison bridge before automating cross-format conclusions.
Subprocess containment
is not an OS security sandbox and no proposal automatically enters project generation.
