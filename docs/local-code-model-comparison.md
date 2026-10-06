# Local Code Model Comparison

## Purpose

Compare an instruction-tuned code model with the measured `qwen3:8b` baseline before tuning the
prompt, changing the fidelity validator or considering fine-tuning. This experiment measures
node-code generation on synthetic task cells, not semantic planning or complete-notebook conversion.

The candidate is [`qwen2.5-coder:7b`](https://ollama.com/library/qwen2.5-coder:7b), an Ollama
Q4_K_M distribution of Qwen's instruction-tuned code model. The
[publisher's model card](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) documents its
code specialization and Apache-2.0 license. Its approximately 4.7 GB download is a local model
installation, not a hosted API subscription. Download size is not a total runtime-memory estimate.

## Controlled Protocol

Keep these inputs and policies identical to the expanded
[baseline](behavioral-code-benchmark.md#expanded-dataset-baseline):

- Node dataset `tests/fixtures/evaluation/node_code/v2`: eight reviewed requests.
- Behavioral dataset `tests/fixtures/evaluation/behavioral/v2`: seventeen reviewed scenarios.
- Prompt `node-code-v4` with deterministic parameter evidence enabled.
- Validator `node-code-validation-v4`; rejected proposals are never executed.
- Existing Ollama transport: JSON-schema output, non-streaming requests, `think: false` and
  `temperature: 0`. Model-specific chat templates remain part of each model distribution.
- Provider timeout 120 seconds; subprocess execution timeout 10 seconds per scenario.
- One proposal per node per run, with all linked scenarios evaluated only after static acceptance.
- Three sequential live runs on the same machine, then offline replay of the first candidate run.

No prompt retries, output repairs, corpus changes or validator exceptions are introduced for the
candidate. A provider error is an experimental outcome, not permission to silently change transport
settings. Temperature zero does not guarantee byte-identical responses on all hardware and runtimes.
The existing transport does not explicitly pin a random seed or context length.

Record exact installed model digests, Ollama and Python versions and repository revisions in each
artifact. Do not commit raw responses; they remain in ignored `generated/` with notebook source.

## Reproduction

Install the candidate explicitly; the benchmark itself never downloads models:

```bash
ollama pull qwen2.5-coder:7b
```

Run the candidate three times with distinct output paths:

```bash
for run in 1 2 3; do
  uv run --python 3.12 notebook-to-kedro behavioral-benchmark run \
    tests/fixtures/evaluation/behavioral/v2 \
    tests/fixtures/evaluation/node_code/v2 \
    "generated/qwen25-coder-7b-v2-run-${run}.json" \
    --project-root . \
    --ollama-model qwen2.5-coder:7b \
    --include-parameter-evidence \
    --allow-untrusted-code-execution
done
```

The loop above uses Bash syntax; on PowerShell, issue the same CLI command three times with
filenames ending in `run-1.json`, `run-2.json` and `run-3.json`.

Replay run 1 without contacting the model:

```bash
uv run --python 3.12 notebook-to-kedro behavioral-benchmark replay \
  generated/qwen25-coder-7b-v2-run-1.json \
  tests/fixtures/evaluation/behavioral/v2 \
  tests/fixtures/evaluation/node_code/v2 \
  generated/qwen25-coder-7b-v2-run-1-replay.json \
  --project-root . \
  --allow-untrusted-code-execution
```

Compare the existing baseline artifact with each live candidate run:

```bash
uv run --python 3.12 notebook-to-kedro behavioral-benchmark compare \
  generated/qwen3-8b-v2-baseline-run-1.json \
  generated/qwen25-coder-7b-v2-run-1.json \
  --output generated/qwen3-vs-qwen25-coder-7b-v2-run-1.json
```

Also compare candidate run 1 against candidate runs 2 and 3 and its replay to separate
between-model differences from repeated-run variability. Output writes are exclusive: use fresh
paths when repeating the experiment. Baseline artifacts are local evidence, not distributed with
the repository; recreate a baseline using the same corpus and policies when they are unavailable.

## Interpretation

Report static node acceptance, matches among evaluated scenarios and end-to-end matches separately.
The primary end-to-end denominator remains seventeen, including scenarios blocked by static or
provider failures. Rejected code has unknown behavioral equivalence; it is not a runtime mismatch.
Scenarios sharing a proposal are correlated rather than independent generation samples.

Compare all per-node outcomes, especially the two original strict-contract rejection cases, and
retain every duration rather than selecting the fastest run. Provider durations include validation;
worker durations include process setup. Model loading, GPU residency and background load can affect
latency, so these measurements alone do not establish model throughput or production performance.
An offline replay has zero provider duration and cannot support a model-latency comparison.

Only choose a candidate for a further pilot after inspecting acceptance and behavioral regressions.
Even a perfect result on these eight tasks would not establish accuracy on arbitrary notebooks or
remove the need for review and stronger production execution isolation.

## Observed Results

Three live candidate runs on 2026-10-02 used Ollama `0.35.0`, Python `3.12.14` on Windows,
repository revision `0a259927d0db954fdadb4b9d4d1b18afc29543f3` and candidate model digest
`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` (Q4_K_M).
The baseline used revision `4aaf9da417e444aac9dcbe274f274d865e46e357`; the revisions differ only
in documentation. Code, corpus files, dependency lockfile and configuration were unchanged.
All eight recorded request objects and source hashes matched between models, as did artifact
configuration, prompt and validator versions. A local `/api/ps` snapshot during the first candidate
run reported a 4096-token context and model residency entirely in VRAM; that snapshot is an
observation, not a permanent resource guarantee or a versioned benchmark-artifact field.

| Model / run | Accepted nodes | End-to-end matches | Provider duration | Execution duration |
| --- | --- | --- | --- | --- |
| `qwen3:8b` baseline 1 | 6/8 (75%) | 15/17 (88.24%) | 39.79 s | 15.77 s |
| `qwen3:8b` baseline 2 | 6/8 (75%) | 15/17 (88.24%) | 32.57 s | 13.84 s |
| `qwen3:8b` baseline 3 | 6/8 (75%) | 15/17 (88.24%) | 32.42 s | 16.02 s |
| `qwen2.5-coder:7b` run 1 | 7/8 (87.5%) | 16/17 (94.12%) | 65.34 s | 18.95 s |
| `qwen2.5-coder:7b` run 2 | 7/8 (87.5%) | 16/17 (94.12%) | 30.47 s | 16.91 s |
| `qwen2.5-coder:7b` run 3 | 7/8 (87.5%) | 16/17 (94.12%) | 47.36 s | 12.75 s |
| Candidate run 1 offline replay | 7/8 (87.5%) | 16/17 (94.12%) | Not comparable | 20.61 s |

Every candidate run evaluated sixteen scenarios and matched all sixteen, including the five
expected exceptions. One scenario was not evaluated because its proposal failed static validation.
There were no provider errors, invalid response contracts, behavioral mismatches or worker errors.
All eight raw responses were byte-identical across the three live candidate runs. Offline replay
reproduced the same acceptance and scenario outcomes without model calls.

| Node case | `qwen3:8b` | `qwen2.5-coder:7b` | Candidate matching / linked scenarios |
| --- | --- | --- | --- |
| `aggregate-orders` | Accepted | Accepted | 3/3 |
| `custom-ratio` | Accepted | Accepted | 2/2 |
| `date-features` | Accepted | Accepted | 3/3 |
| `encode-categories` | Accepted | Accepted | 3/3 |
| `evaluate-regression` | Rejected | Rejected | 0/1, not evaluated |
| `fill-missing` | Accepted | Accepted | 1/1 |
| `join-customers` | Accepted | Accepted | 3/3 |
| `split-holdout` | Rejected | Accepted | 1/1 |

The candidate kept the split import at module level, used the exact planned parameter substitutions
and returned the four reviewed outputs; its split scenario matched the independent expected arrays.
Both models still omitted the final standalone `mae` expression in `evaluate-regression`.
The unchanged AST-fidelity validator rejected that proposal before execution. This is a strict
contract failure, not an observed runtime mismatch or proof that the metric value would differ.

Each comparison against baseline run 1 recorded one improved proposal and one newly matching
scenario, with zero proposal or evaluated-scenario regressions. Acceptance increased by 12.5
percentage points and end-to-end matching by approximately 5.88 points on the same dataset.
Candidate repeated-run and replay comparisons recorded unchanged statuses. Provider latency was
marked non-comparable for replay. Live timings varied, and the first candidate run was the first
use of a newly installed model; these data do not establish a stable speed advantage.

### Evidence And Decision

Canonical artifact hashes identify the private evidence in `generated/`:

| Artifact filename | Canonical artifact SHA-256 |
| --- | --- |
| `qwen25-coder-7b-v2-run-1.json` | `e112d3a31432d45bb2bbf0df92118a58171f8e8d02bd99ac5ee94c37651950d8` |
| `qwen25-coder-7b-v2-run-2.json` | `ef0f36d5c00ca83dd43b2e9e37eed55984626e62891a8ed66750aadbae9863da` |
| `qwen25-coder-7b-v2-run-3.json` | `c99a781733fdf04b171c0d3a73428f6c3e653ea24992a3cbd1b988babe7731bd` |
| `qwen25-coder-7b-v2-run-1-replay.json` | `a6803d746e9292d115a1e51d44020d9bd1bc8eebc785cd5ce2a647e43c5f8e25` |

Cross-model comparisons are `qwen3-vs-qwen25-coder-7b-v2-run-{1,2,3}.json`. Within-candidate
comparisons are `qwen25-coder-7b-v2-run-1-vs-{2,3,replay}.json`. All are local, ignored files.

The code-specialized model is a stronger candidate for the next code-generation pilot on this
evidence, but no application default, prompt, validator or reviewed reference was changed.
No model was trained, and no production notebook conversion was automated by this experiment.

The next experiment should clarify source-statement retention in a versioned prompt while keeping
the validator unchanged. Once these observed cases guide prompt changes, treat them as development
regressions rather than untouched held-out evidence, and add fresh independently reviewed tasks
before claiming broader generalization. Complete notebooks and the structure-planner role still
require separate evaluation.

The subsequent [statement-retention prompt experiment](node-code-statement-retention.md) was
rejected after cross-task regressions on both models. Active prompt selection remains `v4` when
parameter evidence is enabled; the next investigation is deterministic shell assembly under an
explicit contract, without weakening validation or silently repairing rejected responses.

The [body-only measurements](node-body-local-measurements.md) now record three live runs and
three replays per model with the same development corpus and unchanged validator. The code model
passes all eight nodes and seventeen scenarios, while the general model has one parameter-fidelity
rejection. These later runs used Ollama `0.35.1`; they are not a same-runtime full-code/body-only
ablation and do not alter the historical full-code results above.
