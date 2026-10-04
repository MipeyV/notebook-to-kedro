# Statement Retention Prompt Experiment

## Decision

The `node-code-v5` candidate was rejected. Active prompts remain `node-code-v1` by default and
`node-code-v4` with `include_parameter_evidence=True`. Production code, parameter evidence,
request/response schemas, reviewed corpus and validator `node-code-validation-v4` are unchanged.

The candidate retained the final metric expression on both models but introduced more rejections
elsewhere. Fixing one known task is not sufficient justification to promote a prompt that regresses
other reviewed tasks. No rejected output was repaired, executed or written into a generated project.

## Candidate And Provenance

On 2026-10-03, the experiment added four generic instructions to the opt-in prompt:

- Retain every source statement in its original order, including standalone expressions.
- Keep final notebook-display expressions even when they repeat an output variable.
- Indent the source body and apply only the listed parameter substitutions.
- Append the terminal return instead of replacing a source expression.

It also supplied a generic complete-function example for `value = sum(items)` followed by `value`,
showing both the retained expression and the additional return. The example repeated that allowed
imports belong in the separate imports array. It did not use a task, library or output reference
from the evaluation corpus. The default `v1` prompt remained byte-identical.

The complete candidate is archived at commit
`f5252ce230f92137328f1058d8fbe934d418c9e6`. Both reported live artifacts and their replays were
captured from that clean revision before restoring `v4`. A current checkout does not select `v5`.

Both models used Ollama `0.35.0`, Python `3.12.14` on Windows, prompt `node-code-v5`, validator
`node-code-validation-v4`, parameter evidence enabled, a 120-second provider timeout and a
10-second per-scenario worker timeout. Exact model digests were:

- `qwen3:8b`, Q4_K_M:
  `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
- `qwen2.5-coder:7b`, Q4_K_M:
  `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`.

The reviewed `v2` corpora remained eight node requests and seventeen scenarios. Recorded requests,
source hashes and benchmark configuration matched the corresponding `v4` baseline. These cases
were already used to diagnose the prompt and are development regressions, not untouched held-out
evidence for prompt generalization.

Earlier rules-only and body-only example drafts were explored before freezing the complete-function
candidate. Their artifacts came from uncommitted edits and do not identify exact prompt revisions;
they are excluded from the reproducible comparison below. The frozen candidate reproduced the
complete-function exploratory run's code-model outcome.

## Results

Baseline outcomes come from the existing three-run `v4` experiments; the table uses run 1 for
comparisons and timings. Each candidate row is one live run from the archived revision, followed
by one offline replay. The candidate was rejected
after the measured regressions; there is no repeated-live-run stability claim for `v5`.

| Model / prompt | Accepted nodes | End-to-end matches | Provider duration | Execution duration |
| --- | --- | --- | --- | --- |
| `qwen3:8b` / `v4` baseline run 1 | 6/8 | 15/17 (88.24%) | 39.79 s | 15.77 s |
| `qwen3:8b` / `v5` candidate | 6/8 | 13/17 (76.47%) | 40.53 s | 14.89 s |
| `qwen3:8b` / `v5` replay | 6/8 | 13/17 (76.47%) | Not comparable | 14.72 s |
| `qwen2.5-coder:7b` / `v4` baseline run 1 | 7/8 | 16/17 (94.12%) | 65.34 s | 18.95 s |
| `qwen2.5-coder:7b` / `v5` candidate | 3/8 | 6/17 (35.29%) | 30.87 s | 7.52 s |
| `qwen2.5-coder:7b` / `v5` replay | 3/8 | 6/17 (35.29%) | Not comparable | 4.69 s |

All executed scenarios matched. There were no provider errors, invalid JSON-response contracts,
runtime mismatches or execution errors. The candidate blocked four scenarios for `qwen3` and
eleven for the code model through static rejection. Reporting only the 100% evaluated match rate
would hide these losses. Worker durations also depend on how many scenarios reached execution.

| Node case | qwen3 `v4` -> `v5` | Code model `v4` -> `v5` |
| --- | --- | --- |
| `aggregate-orders` | Accepted -> accepted | Accepted -> rejected |
| `custom-ratio` | Accepted -> accepted | Accepted -> accepted |
| `date-features` | Accepted -> accepted | Accepted -> rejected |
| `encode-categories` | Accepted -> rejected | Accepted -> rejected |
| `evaluate-regression` | Rejected -> accepted | Rejected -> accepted |
| `fill-missing` | Accepted -> rejected | Accepted -> rejected |
| `join-customers` | Accepted -> accepted | Accepted -> accepted |
| `split-holdout` | Rejected -> accepted | Accepted -> rejected |

Both metric proposals retained the original final `mae` expression and matched the reviewed metric
scenario. However, the code model added new standalone output expressions to aggregation, dates,
encoding and imputation tasks whose sources did not contain them. Its split proposal placed a
top-level import in `function_code`. These all violated the unchanged contract.

For `qwen3`, encoding gained an unplanned output expression, while imputation omitted the parameter
argument and hardcoded its values. The identical 6/8 aggregate acceptance hides two improved and
two regressed nodes. Comparison recorded two improved scenarios and four regressed scenarios.
The code model had one improved node/scenario but five regressed nodes and eleven regressed scenarios.

The added expression pattern is consistent with over-applying the generic example, but one live
run does not isolate a causal mechanism. Neither the observed gains nor the failures justify a
general model-accuracy claim. Offline replay reproduced each candidate's statuses without model
calls; replay provider latency was correctly marked non-comparable.

## Local Evidence

Raw artifacts remain private in ignored `generated/`. Canonical artifact identities are:

| Filename | Canonical artifact SHA-256 |
| --- | --- |
| `qwen3-8b-prompt-v5-frozen.json` | `85ffe240d3c3164ef4ec003c426a12863a4555ca7052ffea17963c38f3a0bce4` |
| `qwen3-8b-prompt-v5-frozen-replay.json` | `052738a3f77da1d95266167ff5867aad622450eb335ad723bd3e65e9f9b08d2c` |
| `qwen25-coder-7b-prompt-v5-frozen.json` | `6821f4617197c47878cc03d3efacc16f40dacad08cac2ecc71cbdd2694d7bb9f` |
| `qwen25-coder-7b-prompt-v5-frozen-replay.json` | `15c78dd9709f5b3d4825d32faf8f354ae6aa34673403d28c8bee514cf4a34f1a` |

Comparisons are `qwen3-8b-v4-vs-v5.json`, `qwen25-coder-7b-v4-vs-v5.json` and the two files
ending in `prompt-v5-vs-replay.json`. Each replay comparison found unchanged proposal and evaluated
scenario statuses. Historical baseline identities are documented in the
[behavioral benchmark](behavioral-code-benchmark.md) and
[local model comparison](local-code-model-comparison.md).

To reproduce the archived prompt without changing the active checkout, create a fresh worktree:

```bash
git worktree add generated/prompt-v5-reproduction f5252ce230f92137328f1058d8fbe934d418c9e6
cd generated/prompt-v5-reproduction
uv run --python 3.12 notebook-to-kedro behavioral-benchmark run \
  tests/fixtures/evaluation/behavioral/v2 \
  tests/fixtures/evaluation/node_code/v2 \
  generated/new-v5-artifact.json \
  --project-root . \
  --ollama-model qwen2.5-coder:7b \
  --include-parameter-evidence \
  --allow-untrusted-code-execution
```

Use `qwen3:8b` and another fresh output path for the other model. Run only in a controlled
environment: subprocess execution is not an OS sandbox. Existing files are never overwritten.
Different timestamps and timings produce different artifact hashes even with identical outcomes.

## Next Experiment

Keep `v4` as the active opt-in prompt and preserve strict validation. Investigate separating the
deterministic function shell (signature, import boundaries and terminal return) from the model's
source-body proposal under an explicit versioned contract, rather than asking prompt prose alone
to guarantee assembly. This design must not automatically repair rejected responses.
The [body-only contract and offline assembler](node-body-contract.md) now implement that boundary;
local provider integration and model measurements remain separate next steps.
Keep the current cases as development regressions and add independently reviewed fresh tasks before
assessing broader generalization. Complete notebooks and structure-planner quality remain separate.
