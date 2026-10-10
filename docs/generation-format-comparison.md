# Corpus-Bound Generation Format Comparison

## Scope

`compare_generation_formats(full_code, node_body)` compares a newly corpus-bound full-code
artifact with a body-only artifact. CLI action `behavioral-benchmark compare-formats` exposes
the same operation. It reads recorded evidence without calling a model or executing code.
Legacy full-code formats, existing comparators and conversion defaults remain unchanged.

The comparison requires identical complete corpus identity: requests, source paths/hashes,
references, negative controls, scenario inputs, expectations and comparator policies. Matching
case names alone is insufficient. It lists **all** scenarios, including those not evaluated on
either side, and preserves rejection counts and full end-to-end denominators.

This increment includes offline regression tests and real subprocess reference execution on
the four-node, twelve-scenario [fresh v3 corpus](fresh-node-corpus-v3.md). The implementation
published no model score. Subsequent [same-runtime measurements](fresh-v3-format-measurements.md)
exercise the comparison on twelve complete live artifacts and their replays, without promoting
a provider or integrating generated proposals into projects.

## CLI

Use fresh paths and the same model, repository revision and runtime for both live runs:

```bash
uv run notebook-to-kedro behavioral-benchmark run tests/fixtures/evaluation/behavioral/v3 tests/fixtures/evaluation/node_code/v3 generated/full-v3.json --proposal-format bound-full-code --ollama-model your-local-model --ollama-timeout 120 --include-parameter-evidence --allow-untrusted-code-execution
uv run notebook-to-kedro behavioral-benchmark run tests/fixtures/evaluation/behavioral/v3 tests/fixtures/evaluation/node_code/v3 generated/body-v3.json --proposal-format node-body --ollama-model your-local-model --ollama-timeout 120 --allow-untrusted-code-execution
uv run notebook-to-kedro behavioral-benchmark compare-formats generated/full-v3.json generated/body-v3.json --output generated/formats-v3.json
uv run notebook-to-kedro behavioral-benchmark replay generated/full-v3.json tests/fixtures/evaluation/behavioral/v3 tests/fixtures/evaluation/node_code/v3 generated/full-v3-replay.json --proposal-format bound-full-code --allow-untrusted-code-execution
```

`bound-full-code` selects an additional envelope, not a different provider or prompt. Enable
`--include-parameter-evidence` to match body mode's mandatory evidence setting. Run and replay
require renewed explicit execution consent. Replay preserves byte/capture limits; pass the
original `--execution-timeout` when it was non-default. `--project-root` resolves source paths.

The two comparison arguments have fixed roles: bound full-code baseline, body-only candidate.
Omit `--output` to print JSON. Output files are published exclusively and never overwritten.
Legacy files, swapped formats, incompatible controls and malformed evidence return exit code 1;
invalid CLI options return argparse's exit code 2. There is no format inference or historical
migration command. Subprocesses provide fault containment, **not an OS security sandbox**.

## Full-Code Evidence

`run_corpus_bound_code_benchmark` snapshots the supplied typed corpus **before** provider calls
and delegates to the unchanged full-code benchmark. `CorpusBoundCodeBenchmarkReport` carries
that snapshot, its canonical SHA-256 and the ordinary report. Use
`create_corpus_bound_code_artifact(report, provenance, configuration)` to archive it.

The new schema `1.0` envelope has exactly five fields:

```text
schema_version
artifact_kind = "corpus-bound-full-code"
corpus_sha256
corpus = {behaviors: [...], nodes: [...]}
benchmark = existing full-code behavioral artifact
```

The snapshot's canonical representation matches body mode's corpus hash. Cases are sorted by
ID for identity, while each case preserves ordered interfaces and statements. The whole outer
envelope has a separate identity through `corpus_bound_code_artifact_sha256`.

Dedicated dictionary/file APIs reject unknown fields, unsupported versions, duplicate JSON keys,
bad corpus/report hashes and legacy files. They check exact source/request bindings, scenario
coverage for accepted proposals, raw/parsed full-code response consistency and current static
validation. Recorded comparisons are recomputed from stored execution results and corpus
expectations; loading does **not** execute code again. Provider errors contain no invented
response, invalid JSON remains rejected and parsed invalid code is retained but never executed.

`write_corpus_bound_code_artifact` revalidates mutable dictionaries before exclusive atomic
publication. `load_corpus_bound_code_artifact` uses the explicit envelope. Replay requires the
exact complete corpus, reparses recorded raw responses, renews execution consent and uses no
provider/network calls. Create a replay artifact with `mode="replay"` and the **outer source**
hash, not the embedded report hash.

No legacy artifact is retroactively assigned today's corpus identity. Configuration and
provenance remain caller-supplied evidence, not signed attestations. Hashes detect accidental
changes, not maliciously recomputed content or independent human review. Stored results can be
checked for consistency, but only a new controlled execution can verify their behavior again.

## Comparison Controls

Both formats are revalidated before comparison. Required controls are:

- Exact corpus digest, sources, requests, scenario coverage and internally consistent summaries.
- Identical provider/model names, validator version and execution policy.
- Identical provider URL/timeout, parameter-evidence setting and execution time/byte limits.
- Identical recorded Python version and platform, including comparisons involving replay.
- For **two live runs**, known and matching repository revision, Ollama version and model digest.
  Missing values are rejected, even when both sides have null metadata.

Schema `1.0`, tagged `generation-format-comparison`, records both outer artifact hashes,
configurations, provenance, prompt identities, body/assembly/evidence versions, full summaries,
per-node diagnostics, metric deltas and proposal/scenario changes. Scope is
`recorded-live-controls` for two eligible live runs; otherwise it is `outcomes-only`.

Prompt identities deliberately may differ: this measures the full-code and body-only paths with
their respective prompts, **not assembly alone**. Recorded control equality is necessary but
does not attest GPU residency/load, seeds/context settings, dependency identity or a clean
worktree. It is not proof of a fully causal format ablation.

Provider duration measures the entire proposal phase, including prompt/provider, parsing,
assembly where applicable and validation. Its delta is null whenever either artifact is a replay.
Execution durations are observed subprocess timings, not inference latency. Offline reference
providers can compare outcomes through replay but cannot claim eligible live measurements without
actual runtime identity.

## Measurement Status

After review and merge, both local models were run on immutable v3 with unchanged prompts and
contemporaneous full-code/body-only controls. The linked report preserves repeated runs,
rejections, raw evidence, offline replay and an initial Windows infrastructure interruption.
Historical v2 measurements remain development evidence with a runtime difference, not controlled comparisons
retroactively repaired by this envelope. Full notebooks and project equivalence remain separate.
