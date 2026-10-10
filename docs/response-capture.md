# Durable Response Capture

## Scope

Response capture is opt-in evidence storage for behavioral benchmarks, not another model or a
scored benchmark format. It supports `full-code`, `bound-full-code` and `node-body` without changing
their prompts, parsers, assembler, validator, execution consent or final artifact schemas.

Use a new private capture directory for each run. The original complete corpus, source hashes,
requests, reviewed references and scenarios are recorded before generation, together with provider,
model, prompt, validator, execution-policy, configuration and environment provenance. The CLI
collects this provenance before generation when capture is selected; it includes optional Ollama
version/model metadata, not continuous runtime monitoring.

```bash
uv run notebook-to-kedro behavioral-benchmark run \
  tests/fixtures/evaluation/behavioral/v3 \
  tests/fixtures/evaluation/node_code/v3 \
  generated/captured-v3-live.json \
  --project-root . \
  --ollama-model qwen3:8b \
  --proposal-format node-body \
  --capture-dir generated/captured-v3-responses \
  --allow-untrusted-code-execution
```

The command still publishes its usual final artifact only after a completed benchmark. Without
`--capture-dir`, existing CLI behavior and filesystem writes are unchanged.

## Publication And Failure Boundaries

The directory contains:

- `manifest.json`: schema `1.0`, kind `behavioral-response-capture`, the complete corpus and run metadata.
- `attempts/<request-sha256>.json`: an exclusive reservation published before contacting the provider.
- `responses/<request-sha256>.json`: the exact returned assistant-content string and UTF-8 SHA-256,
  or an expected provider-error code/message, bound to that request and the manifest digest.

All JSON publications use the existing atomic, exclusive writer: a flushed/fsynced temporary file
is linked to a new destination, never replacing an existing file. Raw content is not reformatted,
repaired or parsed before publication; whitespace and Unicode survive the outer JSON encoding.
The capture is not a copy of the complete HTTP response or a wire-level transport log.

A provider outcome must be published before it is returned to the benchmark parser, assembler,
validator or executor. A write failure aborts instead of executing uncaptured code. A second call
for the same request in that capture is refused before contacting the provider, including when only
its reservation survives. Concurrent duplicate callers cannot both reserve the same request.
The capture directory itself must be new; it is not reopened automatically to continue generation.

An unexpected provider exception, interrupted call or failed disk write leaves a missing outcome.
Previously published responses remain inspectable. There is no automatic model retry or invented
provider failure for an unknown outcome. Use a separately identified new run if generation must be
repeated. A capture cannot guarantee saving a response while the disk is unavailable, nor provide
power-loss durability beyond the filesystem and existing publication primitive.

## Inspect And Recover

Inspection makes no model call and does not parse or execute generated code:

```bash
uv run notebook-to-kedro behavioral-benchmark capture-info generated/captured-v3-responses
```

It reports expected/recorded counts, provider errors, missing node IDs and evidence hashes.
`complete: true` means every node has a published provider outcome, including errors. It does not
mean responses are valid or faithful: `benchmark_completed` is always `false` for a capture.
The Python `load_response_capture` API also exposes exact recorded responses for partial captures.

Only a complete capture can produce a recovered benchmark:

```bash
uv run notebook-to-kedro behavioral-benchmark recover \
  generated/captured-v3-responses \
  tests/fixtures/evaluation/behavioral/v3 \
  tests/fixtures/evaluation/node_code/v3 \
  generated/captured-v3-recovered.json \
  --project-root . \
  --allow-untrusted-code-execution
```

Recovery infers the response format from the manifest. It requires the exact complete supplied
corpus, current notebook source verification, a supported validator/policy and renewed execution
consent. Recorded execution bounds are reused; this command does not override them. It re-parses
raw responses, assembles bodies when selected, applies strict validation and executes only accepted
proposals. Invalid JSON/code and expected provider errors remain in the complete denominator.
It neither contacts Ollama (including metadata endpoints) nor regenerates missing responses.

The output uses the existing selected artifact envelope with `mode: replay`, current local
environment provenance and `source_artifact_sha256` equal to the capture snapshot digest. Here the
source identity refers to captured provider evidence, not an earlier scored benchmark. Recovery
proposal durations are zero; execution durations are newly observed. Standard replay/comparison
of the resulting completed artifacts remains available and does not treat recovery as live latency.

## Python API

`create_response_capture` wraps an existing `NodeCodeProvider` or `NodeBodyProvider` after preflight.
Pass explicit provenance, configuration, prompt version, response format, project root and consent;
then use the returned provider in the corresponding existing benchmark runner.

`load_response_capture`, `response_capture_summary` and `recover_response_capture` expose inspection
and offline recovery. Loaded mutable dictionaries are revalidated before recovery, including exact
keys, corpus/request/manifest bindings, raw-content hashes, outcome types and the snapshot digest.
Duplicate JSON keys and duplicate/unknown response identities are rejected.

The manifest digest identifies its canonical content. The capture snapshot digest identifies the
manifest plus sorted published outcomes; it changes as outcomes are added. Attempt reservations
are checked on load but are not part of that snapshot digest. Hashes detect corruption/mixing;
they are not signatures and do not authenticate an author or establish model-code correctness.

## Limits And Data Handling

Captures contain source code, scenario inputs, reviewed references and untrusted model content.
Keep them private, retain logs with the evidence, and follow local retention/access policies.
There is no encryption, cloud upload, model download, training or automatic project generation.
Process isolation remains fault containment, not an OS security sandbox.

Capture reservation/publication I/O is included in live proposal duration, which already includes
parsing/validation. Do not compare captured and uncaptured runs as pure model-inference latency;
the sidecar capture protocol is not added to legacy artifact configuration schemas.
Offline reference recovery validates infrastructure, not live model accuracy or whole-notebook
conversion quality. The next milestone is an independently reviewed complete-notebook pilot.
