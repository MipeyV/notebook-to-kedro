# Behavioral Code Benchmark

## Scope

`run_behavioral_code_benchmark` measures one node-code provider against the independent reviewed
node and behavioral corpora. It requests each node exactly once, validates every raw response, and
executes accepted proposals over their linked behavioral scenarios. The frozen `v1` dataset contains
four nodes and five scenarios. The expanded `v2` dataset contains eight nodes and seventeen scenarios
and preserves every `v1` case. These dataset revisions use the same case schema `1.0`.

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
  tests/fixtures/evaluation/behavioral/v2 \
  tests/fixtures/evaluation/node_code/v2 \
  generated/behavioral-code-qwen3-8b-v2.json \
  --project-root . \
  --ollama-model qwen3:8b \
  --include-parameter-evidence \
  --allow-untrusted-code-execution
```

The default test suite uses deterministic fake providers and workers. It does not contact Ollama or
execute model output. Real runs require an already downloaded local model; the benchmark never pulls
a model automatically. The command also reads the local `/api/version` and `/api/tags` endpoints to
record the exact Ollama version and full model digest.

Use matching node and behavioral dataset revisions. Use `v1` to reproduce the measurements below
and `v2` for the expanded evaluation. Compare model or prompt variants on the same dataset; the
comparison CLI rejects artifacts containing different node IDs. The historical `v1` score cannot
be treated as a baseline percentage for the larger `v2` dataset without a new run.

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
  generated/behavioral-code-qwen3-8b-v2.json \
  tests/fixtures/evaluation/behavioral/v2 \
  tests/fixtures/evaluation/node_code/v2 \
  generated/behavioral-code-qwen3-8b-v2-replay.json \
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

## Repeated Local Baseline

Three consecutive runs on 2026-10-02 used the same `qwen3:8b` digest, Ollama `0.35.0`, Python
`3.12.14`, prompt `node-code-v4` and validator `node-code-validation-v4`. The model was
already loaded locally; the first run includes a larger warm-up cost.

| Run | Accepted nodes | End-to-end matches | Provider duration | Execution duration |
| --- | --- | --- | --- | --- |
| 1 | 2/4 | 3/5 (60%) | 29.56 s | 3.67 s |
| 2 | 2/4 | 3/5 (60%) | 16.01 s | 3.19 s |
| 3 | 2/4 | 3/5 (60%) | 15.59 s | 3.19 s |

All proposal and scenario statuses were identical across the three runs. Three of four raw responses
were byte-identical. The `split-holdout` response varied only by one explanatory word in
`review_notes`; its generated function remained identical and was rejected every time for the same
function-local import.

The two static failures were systematic:

- `evaluate-regression` omitted the source cell's final standalone `mae` expression;
- `split-holdout` duplicated the top-level import inside the generated function.

An offline replay of run 1 reproduced 2/4 accepted nodes and 3/5 end-to-end matches without Ollama.
The comparison correctly treated replay provider latency as non-comparable. These repeated results
show deterministic outcome stability for this model and configuration, but the corpus remains too
small to justify prompt tuning or a general accuracy claim.

## Expanded Dataset Baseline

Three live runs on 2026-10-02 evaluated dataset `v2` at repository revision
`4aaf9da417e444aac9dcbe274f274d865e46e357` without changing the model, prompt or validator.
They used `qwen3:8b` (Q4_K_M), digest
`500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`, Ollama `0.35.0`,
Python `3.12.14` on Windows, prompt `node-code-v4` and validator `node-code-validation-v4`.
Parameter evidence was enabled, provider timeout was 120 seconds, and the
`validated-local-subprocess-v1` execution policy used a 10-second timeout per scenario.

| Run | Accepted nodes | End-to-end matches | Provider duration | Execution duration |
| --- | --- | --- | --- | --- |
| 1 | 6/8 (75%) | 15/17 (88.24%) | 39.79 s | 15.77 s |
| 2 | 6/8 (75%) | 15/17 (88.24%) | 32.57 s | 13.84 s |
| 3 | 6/8 (75%) | 15/17 (88.24%) | 32.42 s | 16.02 s |
| Run 1 offline replay | 6/8 (75%) | 15/17 (88.24%) | Not comparable | 15.29 s |

Every run evaluated fifteen scenarios and matched all fifteen, including five expected exceptions.
Two scenarios were not evaluated because their proposals failed static validation. There were no
provider errors, invalid response contracts, behavioral mismatches or execution errors. Provider
durations include validation; execution durations include subprocess setup and are not direct
function runtimes. The slower first run alone does not establish the cause of the timing difference.

| Node case | Static outcome in all three runs | Matching / linked scenarios |
| --- | --- | --- |
| `aggregate-orders` | Accepted | 3/3 |
| `custom-ratio` | Accepted | 2/2 |
| `date-features` | Accepted | 3/3 |
| `encode-categories` | Accepted | 3/3 |
| `evaluate-regression` | Rejected: source-body AST changed | 0/1, not evaluated |
| `fill-missing` | Accepted | 1/1 |
| `join-customers` | Accepted | 3/3 |
| `split-holdout` | Rejected: function-local import | 0/1, not evaluated |

All four added tasks passed all twelve linked scenarios. On the unchanged original subset the
result remains 2/4 accepted nodes and 3/5 matches. Consequently, 88.24% on `v2` is not a model
improvement over 60% on `v1`: only the evaluated dataset changed. Scenarios share one proposal
per node, so seventeen scenarios are not seventeen independent code-generation samples.

The same two rejection causes persisted. `evaluate-regression` omitted the final standalone `mae`
expression; `split-holdout` duplicated an allowed top-level import inside its function. These violate
the strict fidelity contract. The benchmark did not execute either rejected proposal, so their
behavioral equivalence is unknown; these outcomes must not be described as runtime mismatches.

Seven of eight raw responses were byte-identical across all three runs. The split node's review
note added only the word `The` in runs 2 and 3; all eight generated functions remained identical.
Run 1 comparisons against runs 2 and 3 and its offline replay found zero proposal regressions and
zero evaluated-scenario regressions. Replay performed no model calls and recorded zero provider
duration; the comparison marked that latency as non-comparable.

### Local Evidence

Raw artifacts remain private in ignored `generated/`. Artifact schema `1.0` embeds the complete
report, raw responses and runtime provenance. The following full artifact hashes identify this
measurement independently of rounded table values:

| Artifact filename | Canonical artifact SHA-256 |
| --- | --- |
| `qwen3-8b-v2-baseline-run-1.json` | `2610bc6e27ad683966f48b5924c26a0096e1afb66a625af3e9a709ed567651d9` |
| `qwen3-8b-v2-baseline-run-2.json` | `93a3d1c125d82ec48e91a75c039968359086cdb4c81c21739c135bf7dc17c10a` |
| `qwen3-8b-v2-baseline-run-3.json` | `2775c48f40af8874c230bd7440e7c0f5c95034431f0e1ebf1a1336059a5c9c69` |
| `qwen3-8b-v2-baseline-run-1-replay.json` | `4820318ed80c319b472c9116d25c9f46deae4973a552c5e959f42f4b1af82fdb` |

Comparison files use the prefix `qwen3-8b-v2-baseline-run-1-vs-` and suffixes `2.json`, `3.json`
and `replay.json`. To repeat the experiment, use the run/replay commands above with these corpus
directories and fresh output paths: artifacts are never overwritten. New timestamps and durations
will change artifact hashes even when generated code and outcomes remain identical.

This is a repeated local development observation over eight synthetic task cells, not a production
accuracy estimate, a complete-notebook conversion result or an assessment of structure-planner
quality. The next comparison should evaluate another local code model on exactly the same dataset,
prompt and validator before tuning prompts or considering fine-tuning.

That [controlled comparison](local-code-model-comparison.md) now records three `qwen2.5-coder:7b`
runs and an offline replay at 7/8 accepted nodes and 16/17 end-to-end matches. The split node passed
without a regression on the remaining cases; the metric node's source-expression omission remained
statically rejected. The comparison documents exact provenance, unchanged inputs, timings and limits.

The subsequent [statement-retention prompt experiment](node-code-statement-retention.md) corrected
the metric omission but regressed end-to-end results on both models. Its archived `v5` candidate
is not active; opt-in prompt `v4` and the original comparison results remain the current baseline.
