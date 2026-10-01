# Behavioral Code Benchmark

## Scope

`run_behavioral_code_benchmark` measures one node-code provider against the independent reviewed
node and behavioral corpora. It requests each of the four nodes exactly once, validates every raw
response, and executes only accepted proposals over their linked behavioral scenarios. The current
corpus contains four nodes and five scenarios because the custom-ratio node has both a successful
case and an expected missing-column exception.

All corpus links, notebook hashes, reviewed source cells, reference responses and interfaces are
preflighted before the first provider call. Empty corpora, duplicate identities, stale notebooks,
unlinked nodes and invalid references abort without contacting the provider.

This benchmark is independent from the 26-task V1 node-code benchmark. It uses a smaller held-out
corpus with manually reviewed node references and runtime expectations. It is a development signal,
not an estimate for arbitrary notebooks.

## Outcomes And Metrics

Report schema `1.0` records provider, model, prompt, validator and execution-policy provenance. Each
node proposal retains its request, raw response, parsed response, diagnostic, provider duration and
all linked proposal-evaluation reports. Reports contain notebook source and untrusted model output;
keep them private unless reviewed.

Proposal statuses are:

| Status | Meaning |
| --- | --- |
| `accepted` | Parsing and request-specific static validation passed. |
| `provider_error` | The provider reported an expected transport or generation failure. |
| `invalid_response` | The raw output violated the versioned response contract. |
| `invalid_code` | The parsed proposal failed static validation and was never executed. |

The summary exposes separate denominators:

- **Accepted rate:** accepted nodes divided by all requested nodes.
- **Evaluated match rate:** matching scenarios divided only by executed scenarios.
- **End-to-end match rate:** matching scenarios divided by all reviewed scenarios, including those
  blocked by provider, parsing or static-validation failures.
- **Not evaluated scenarios:** scenarios whose shared node proposal did not reach execution.
- **Mismatch scenarios:** completed executions whose observable behavior differed.
- **Execution errors:** setup, timeout, process or serialization failures, distinct from mismatches.
- **Durations:** provider request-and-validation time and isolated execution time are reported
  separately.

The end-to-end rate is the primary model-development measure. Reporting only the evaluated match
rate would hide rejected proposals and inflate the apparent result.

## Local Run

Proposal execution is opt-in because a subprocess is fault containment, not an OS sandbox. Static
validation constrains the response to the source-derived node body, but the original notebook code
can still access the filesystem or network. Run only in a controlled environment.

```bash
uv run notebook-to-kedro behavioral-benchmark run \
  tests/fixtures/evaluation/behavioral/v1 \
  tests/fixtures/evaluation/node_code/v1 \
  generated/behavioral-code-qwen3-8b-v1.json \
  --project-root . \
  --ollama-model qwen3:8b \
  --include-parameter-evidence \
  --allow-untrusted-code-execution
```

The default test suite uses deterministic fake providers and workers. It does not contact Ollama or
execute model output. Real runs require an already downloaded local model; the benchmark never pulls
a model automatically. The command also reads the local `/api/version` and `/api/tags` endpoints to
record the exact Ollama version and full model digest.

## Reproducible Artifacts

Artifact schema `1.0` wraps the complete benchmark report without dropping raw model responses. It
records:

- the canonical report SHA-256;
- live or replay mode and, for replay, the complete source-artifact SHA-256;
- repository revision, Python version, platform, Ollama version and model digest;
- prompt and validator versions from the embedded report;
- provider, parameter-evidence and bounded execution settings.

Artifact and comparison writes are atomic and exclusive. Parent directories are created, but an
existing output is never replaced. Reports contain notebook source and model output and must be
treated as potentially sensitive evidence.

Replay parses and statically validates every stored raw response again, then re-executes only the
responses accepted by the current validator. It makes no Ollama request:

```bash
uv run notebook-to-kedro behavioral-benchmark replay \
  generated/behavioral-code-qwen3-8b-v1.json \
  tests/fixtures/evaluation/behavioral/v1 \
  tests/fixtures/evaluation/node_code/v1 \
  generated/behavioral-code-qwen3-8b-v1-replay.json \
  --project-root . \
  --allow-untrusted-code-execution
```

Compare two artifacts on static acceptance, end-to-end behavior, per-node and per-scenario changes,
execution duration and live-provider latency:

```bash
uv run notebook-to-kedro behavioral-benchmark compare \
  generated/baseline.json \
  generated/candidate.json \
  --output generated/comparison.json
```

Provider latency is comparable only between two live artifacts. Replay proposal durations are zero
by definition and are never presented as a model-latency delta.

## Initial Local Observation

One run on 2026-09-28 used `qwen3:8b` (Q4_K_M), model digest
`500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`, Ollama `0.34.4`,
Python `3.12.14`, prompt `node-code-v4` and validator `node-code-validation-v4`.

| Measure | Observed result |
| --- | --- |
| Node proposals | 4 |
| Statically accepted | 2/4 (50%) |
| Reviewed scenarios | 5 |
| Evaluated scenarios | 3/5 |
| Matches among evaluated scenarios | 3/3 (100%) |
| End-to-end behavioral matches | 3/5 (60%) |
| Mismatches / execution errors | 0 / 0 |
| Provider errors / invalid responses / invalid code | 0 / 0 / 2 |
| Provider total / mean duration | 24.10 s / 6.03 s |
| Isolated execution duration | 4.25 s |

The custom-ratio proposal passed both its normal and expected-exception scenarios. The fill-missing
proposal also matched. The evaluate-regression proposal changed the reviewed body AST and the
split-holdout proposal introduced a function-local import; both were rejected before execution.

This is one run over a very small synthetic corpus. The 100% evaluated match rate means that static
validation was effective for the accepted subset; it does not erase the two rejected nodes. The
honest current end-to-end observation is 60%, not a general model-accuracy claim.
