# Fresh V3 Full-Code And Body-Only Measurements

## Scope And Frozen Protocol

On 2026-10-10, twelve complete local model runs measured the unchanged four-node,
twelve-scenario [v3 corpus](fresh-node-corpus-v3.md): three runs per model and format,
followed by twelve offline replays. The corpus-creation and comparison PRs had been merged
before measurement. These are synthetic independent tasks with supplied interfaces, not
complete notebooks, a structure-planner evaluation or production accuracy estimates.

The protocol was frozen before the complete series at `2026-10-10T13:12:53.480506+00:00`:

- Repository `39d2127ba32847c1ad927266c5057bdfb02a4d99`, clean tracked worktree throughout live
  runs and replay; source, fixture and dependency-lock fingerprints checked before/after generation.
- Python `3.12.14`, Windows `win32`, Ollama `0.40.2`, loopback `http://localhost:11434`.
- Locked environment including pandas `3.0.5`, NumPy `2.5.2`, SciPy `1.18.0`, scikit-learn
  `1.9.0`, nbformat `5.11.1` and Kedro `1.5.0`.
- Full-code prompt `node-code-v4` with exact parameter evidence; body prompt `node-body-v1`,
  body schema `1.0`, assembly `node-body-assembly-v1` and unchanged `node-code-validation-v4`.
- Existing schema-constrained, non-streaming transport, `think: false`, `temperature: 0`;
  no explicit seed/context override, model warmup, download, training, retry or output repair.
- Provider timeout 120 seconds, execution timeout ten seconds and default byte/capture limits.
  Only statically accepted proposals execute with explicit consent.
- Process-local `TEMP`/`TMP` pointed to `generated/v3-worker-temp-20261010b`, after the
  infrastructure interruption described below. Twelve reference scenarios passed there first.
- A local observer archived exact raw responses or provider errors before returning to the
  unchanged validator/executor. It added no prompt, transformation or retry; its file I/O is
  included in proposal-phase duration. Observations agree with all 48 archived assistant strings.

| Model | Installed Q4_K_M model digest |
| --- | --- |
| `qwen3:8b` | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |
| `qwen2.5-coder:7b` | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` |

The complete corpus SHA-256, including sources, requests, references, negative controls,
scenario inputs/expectations and comparator policies, is unchanged:

```text
1a4fade0462bc0ef58a18cea70099079ff9dd09f8980fb697c5cb64794e32125
```

The fixed order partly balances which format runs first within each numbered pair:

| Sequential block | Exact scheduled order |
| --- | --- |
| `qwen3:8b` | Full 1, body 1, body 2, full 2, full 3, body 3. |
| `qwen2.5-coder:7b` | Body 1, full 1, full 2, body 2, body 3, full 3. |

Version, model digest and `/api/ps` were captured before and after every complete live run.
Initially no model was loaded. Every post-run snapshot reported the selected model only,
4096-token context, runner `llamacpp` and `size_vram == size`. The first run of each model
includes loading. A post-series host query identified an RTX 5070 Ti Laptop GPU with
12,227 MiB and driver `592.01`; it does not attest uninterrupted GPU conditions during inference.
Residency/context snapshots are observations, not permanently pinned settings.

## Infrastructure Interruption

An earlier scheduled `qwen3:8b` full-code run in `generated/format-v3-20261010` was interrupted
by `PermissionError` (`WinError 32`, then `WinError 5`) while the executor's `TemporaryDirectory`
was being cleaned under the default Windows temp root. No complete artifact was published,
and raw responses had not yet been independently archived. The remaining directory was empty
and no Python worker was still running when inspected. This is an incomplete infrastructure
attempt, **not** a scored model rejection, a successful run or a recoverable full trace.

Its original protocol is retained. A separate `format-v3-20261010b` protocol explicitly records
the interruption, workspace temp root and pre-execution response observer. After reference
preflight passed, the entire scheduled series was run under those common settings. Every
complete artifact is retained; none was selected away or rerun to improve a model score.
The complete series runs from the first before-snapshot at `13:13:50` to the final after-snapshot
at `13:22:33` UTC. No fixture, prompt, validator, dependency or application source was modified.

This interruption means there was some preliminary model exposure to v3; do not describe the
complete series as a pristine first-ever model contact. There was no prompt tuning in response
to that attempt or the subsequent scores. The temp-root workaround and durable local observer
do not fix cleanup/checkpoint behavior in the distributed CLI or establish the cause of the lock.
No OS security policy was changed. Upstream infrastructure hardening remains follow-up work.

## Complete Live Results

| Model / format / run | Accepted nodes | End-to-end matches | Proposal phase | Execution |
| --- | --- | --- | --- | --- |
| `qwen3:8b` / full / 1 | 4/4 | 12/12 | 21.85 s | 7.00 s |
| `qwen3:8b` / full / 2 | 4/4 | 12/12 | 17.79 s | 7.11 s |
| `qwen3:8b` / full / 3 | 4/4 | 12/12 | 17.71 s | 7.04 s |
| `qwen3:8b` / body / 1 | 4/4 | 12/12 | 16.43 s | 5.60 s |
| `qwen3:8b` / body / 2 | 4/4 | 12/12 | 16.04 s | 6.12 s |
| `qwen3:8b` / body / 3 | 4/4 | 12/12 | 17.07 s | 6.03 s |
| `qwen2.5-coder:7b` / full / 1 | 3/4 | 9/12 | 26.77 s | 4.94 s |
| `qwen2.5-coder:7b` / full / 2 | 3/4 | 9/12 | 22.35 s | 4.95 s |
| `qwen2.5-coder:7b` / full / 3 | 3/4 | 9/12 | 22.13 s | 5.16 s |
| `qwen2.5-coder:7b` / body / 1 | 4/4 | 12/12 | 38.21 s | 4.71 s |
| `qwen2.5-coder:7b` / body / 2 | 4/4 | 12/12 | 19.98 s | 6.34 s |
| `qwen2.5-coder:7b` / body / 3 | 4/4 | 12/12 | 19.82 s | 5.69 s |

Across each of the three repetitions, both `qwen3:8b` paths and the code model's body-only
path have 100% node acceptance and end-to-end scenario matching. The code model's full-code
path has 75% acceptance and 75% end-to-end matching: one invalid node and three not-evaluated
scenarios per run. Evaluated-only matching is 100% everywhere, but does not hide those omissions.
Complete runs have no provider errors, invalid response contracts, behavioral mismatches or
execution errors. The incomplete infrastructure attempt above is not included in that statement.

| Node / three repetitions | General model full | General model body | Code model full | Code model body |
| --- | --- | --- | --- | --- |
| `cumulative-balance` | Accepted, 3/3 matched | Accepted, 3/3 matched | Accepted, 3/3 matched | Accepted, 3/3 matched |
| `normalize-tags` | Accepted, 3/3 matched | Accepted, 3/3 matched | Accepted, 3/3 matched | Accepted, 3/3 matched |
| `partition-measurements` | Accepted, 3/3 matched | Accepted, 3/3 matched | Rejected, 0/3 evaluated | Accepted, 3/3 matched |
| `rank-candidates` | Accepted, 3/3 matched | Accepted, 3/3 matched | Accepted, 3/3 matched | Accepted, 3/3 matched |

Each row's scenario count is per run, not three new independent task samples. Accepted paths
preserve the tested Unicode normalization/case folding, threshold ties, zero-transaction skip,
overdraft guard, stable tied ranking, index reset and ordered outputs. All four expected exceptions
match on fully accepted paths; the rejected full-code path leaves the partition exception untested.

### Assertion Omission

In every full-code response for `partition-measurements`, `qwen2.5-coder:7b` omits the source guard:

```python
assert limit >= 0, "limit must be non-negative"
```

Its function begins with partition-list initialization and returns the expected three names, but
does not preserve the source precondition. The unchanged validator rejects it with:

```text
Invalid node code: assertions and their enclosing statements must retain source AST and position
```

No rejected code is executed or repaired. All three linked scenarios remain `not_evaluated`,
including nominal and empty cases; this is a static omission, not an observed runtime mismatch.
The negative-limit reference scenario requires `AssertionError`. Body responses from the same
model retain the assertion in the proposed body, and pass all three scenarios. The assembler
supplies signatures/imports/returns, **not missing assertions**; this difference belongs to the
respective model prompt/output paths, not automatic repair by assembly.

## Replay, Comparison And Repeatability

Every complete artifact was replayed with network guards on provider/metadata transports, using
the same ten-second worker limit and workspace temp root. Exact raw responses, parsed bodies,
assembled/full responses, rejection diagnostics, non-timing summaries, per-scenario comparisons
and all non-timing worker evidence agree with their live sources. Each replay references its
whole source-envelope SHA-256. Provider duration is zero by definition, not faster inference.

| Replay | Accepted nodes | End-to-end matches | Execution |
| --- | --- | --- | --- |
| `qwen3-8b-full-run-1` | 4/4 | 12/12 | 4.82 s |
| `qwen3-8b-full-run-2` | 4/4 | 12/12 | 6.85 s |
| `qwen3-8b-full-run-3` | 4/4 | 12/12 | 7.20 s |
| `qwen3-8b-body-run-1` | 4/4 | 12/12 | 4.86 s |
| `qwen3-8b-body-run-2` | 4/4 | 12/12 | 5.29 s |
| `qwen3-8b-body-run-3` | 4/4 | 12/12 | 7.13 s |
| `qwen25-coder-7b-full-run-1` | 3/4 | 9/12 | 4.50 s |
| `qwen25-coder-7b-full-run-2` | 3/4 | 9/12 | 5.21 s |
| `qwen25-coder-7b-full-run-3` | 3/4 | 9/12 | 6.05 s |
| `qwen25-coder-7b-body-run-1` | 4/4 | 12/12 | 7.21 s |
| `qwen25-coder-7b-body-run-2` | 4/4 | 12/12 | 5.47 s |
| `qwen25-coder-7b-body-run-3` | 4/4 | 12/12 | 6.87 s |

Fifteen comparison files retain metadata, summaries and every scenario denominator:

- Six paired live [format comparisons](generation-format-comparison.md) satisfy exact corpus,
  source, model, configuration, validator, Python/platform, revision, Ollama version and digest
  controls. Body-only improves the code model's partition node and three scenarios in every pair:
  +25 percentage points in acceptance and end-to-end matching, with zero regressions. The general
  model's acceptance and outcomes are unchanged between formats.
- Six paired replay-format comparisons reproduce those outcome changes and are `outcomes-only`;
  provider-duration deltas are null and non-comparable.
- Three body-only between-model comparisons have unchanged acceptance/scenario outcomes, zero
  regressions and zero end-to-end rate delta. This dataset does not favor either model's accuracy
  in body mode, and the specialized code model is not universally better in full-code mode.

Within each model/format, all four raw JSON strings are byte-identical across three complete runs,
including the rejected assertion omission. Parsed/assembled responses and statuses are stable too.
This is observed repeatability with these settings, not a guarantee from temperature zero.

Proposal duration includes prompt/provider, parsing, validation, body assembly where applicable
and observer file I/O. Execution includes subprocess setup. The tables are phase totals, not
whole-experiment wall time or pure inference latency. All durations, including model loading, are
retained. The first code-model body run is slower than its paired full run; body mode is not
uniformly faster. Hardware load, residency and different executed-scenario counts prevent treating
execution-time differences as model speed or comparing 9-scenario and 12-scenario work as equal.

These are contemporaneous **path-plus-prompt** comparisons, not an isolated causal assembly
ablation. Seeds/context were not explicitly pinned, and identical recorded controls do not prove
identical resource conditions. Historical v2 used different tasks and Ollama versions; differences
between v2 and v3 percentages are not improvements on the same benchmark.

## Local Evidence And Reproduction

Raw artifacts remain private in ignored `generated/format-v3-20261010b/`, not in this documentation
commit. Append `.json` to the labels below for live artifacts or `-replay.json` for replays.
All listed artifact hashes are canonical **whole-envelope** SHA-256 identities, not file hashes.

| Label | Live envelope SHA-256 | Replay envelope SHA-256 |
| --- | --- | --- |
| `qwen3-8b-full-run-1` | `65ab47d3c46a59e3a6f1fc396f627e97e7af8c6d1a3d0c3ff40bbcf7b16feb5f` | `cec2ce8271f08961566e35cf8ea8fa010c280a73a4a51999d2b6f754df2361bf` |
| `qwen3-8b-full-run-2` | `07ccddf36677fdabf66705fd97fc1764b3eb2db1512487632f2648b09a69ab5d` | `4cd8cb8dfb92dd0b001f055d4ea4d235436a3c4440fd3b9d562c2639743fddff` |
| `qwen3-8b-full-run-3` | `2f5ff1f7c9d0ceb211d08eba5b92937fc6b89aa0014b8912228d9d6a614e7a1e` | `242931cbc5aa3d4010bfe9205b67e1b4d7f78d0c00045fb5106bf66990c9b3e6` |
| `qwen3-8b-body-run-1` | `1a0588239148c6e48db40e1933ae5939f632e00eacbba5ab1bfe946d175c059e` | `28710b3a0ca72385c29e950a25aedfb06832c0aa2dc526e413b4c0f726de5217` |
| `qwen3-8b-body-run-2` | `3adc911424af0b185e0221bb09440a28fd93a0af114caffa72a2e26989937b5c` | `6a4036e90fa8789aa7f4299be1d585247565ee2719d64f218bbb0cfbfc6d59ae` |
| `qwen3-8b-body-run-3` | `741cef022993167219ed719b1369bfbbefd6295edf8d43be8d5f0331748c6225` | `69b566243e511997eb17ecff2ad18a8a9c06e2fff8dcb8784d283bad7a6a02c0` |
| `qwen25-coder-7b-full-run-1` | `6a85aa18d3475b5347a27c43ff890e2a9bc508c03221919973380f77431b9a76` | `e57275a4abd7e5468588eff0e8e79946c4eeffcfba43083ae4c5dd6a2a786a2a` |
| `qwen25-coder-7b-full-run-2` | `5ca422998f1ce471fbc5b65f43bd22e4f083977855fe171fc5553a3cc97081ad` | `407c97cc845dbec999bde637a5fcefa4396332ecafcb6763c272de0a052a11f9` |
| `qwen25-coder-7b-full-run-3` | `b56001f750b05df841d7d1fc8f512d59e77103fe6298d2a118d401d4662f8e01` | `6a2e00d8bdeae0f38364c2e7d2833ba9fde9863b455de4dd02e890bcde6451f8` |
| `qwen25-coder-7b-body-run-1` | `5d442a71a74b4e7aa5dcf07c4b183e935104ea443bd8e4ece35ab9a1680fe68a` | `4af208a3e9b85d8e82f142cfb311031cac758ad73396d86dcbffe6cc1e991b88` |
| `qwen25-coder-7b-body-run-2` | `e4f533a95ab0abb64ec939753a3d524985cf2de23c6efb7c99bc6e17fcb07e1e` | `7961d6c8d4a33f0af94bfa8886465b42f73a1b3a3858eecedbd94be2c716e8b8` |
| `qwen25-coder-7b-body-run-3` | `2f9540610a7fd2d0ef21639b7374f379530eb0edc2ce8e8ba848c8b83f22e604` | `193f4d3a570d28d04aefc01ebcec5cf68fcbccade7eb012a40a1c5747f3cd77c` |

Paired comparisons are `{model}-formats-run-{n}.json` and
`{model}-formats-run-{n}-replay.json`, with model stems `qwen3-8b` / `qwen25-coder-7b`.
Between-model body comparisons are `body-models-run-{n}.json`. `provider-observations/` contains
48 exact response captures; `*-before.json` / `*-after.json` contain 24 environment snapshots.
`reference-preflight.json` records the twelve reference executions. The retained original
interrupted protocol is in `generated/format-v3-20261010/protocol.json`.

File-byte SHA-256 identities for the complete protocol and audit index are:

- `protocol.json`: `3c592d19619dc010a6964485bb146028df0d8df54e1f324ef4103223699d1a48`.
- `audit.json`: `88febd6e5f681ae7d164f9768a040a0379d6703b53cb06ba45277746eeff5412`.
- Frozen local base runner: `531081748b6b82461472292d33c5c24c424a8084f5ddc064fcd9b1ad46a737d8`.
- Replacement temp-root/observer driver:
  `8135ab8cf7141e8cddec74501a5d0db1993cfdfc2cee9e6cf85201224c877592`.

The audit index contains application-source, fixture and dependency-lock fingerprints, comparison file
hashes, per-case evidence, replay checks and stability observations. Hashes are not signatures,
proof of independent annotation or substitutes for access to raw evidence. These local files and
one-off runners are not distributed with the repository.

Reproduce the experiment with the [bound full-code/body commands](generation-format-comparison.md#cli),
these immutable v3 directories, model digests, timeouts and fixed order, using new output paths.
On Windows, create a dedicated workspace temp directory and set process-local `TEMP`/`TMP`
before invoking Python; run reference preflight before scored calls. For equally durable evidence,
archive exact provider responses before returning them to validation, without modifying their
content. A bare CLI reproduction does not include that observer I/O or its early checkpoint.
New timestamps and durations naturally change artifact identities.

## Decision And Next Step

Both body-only candidates pass these four fresh task contracts without weakening validation;
the general model also passes full-code, while the code model reproducibly drops a precondition.
This supports keeping strict validation and body-only generation as pilot candidates, **not**
promoting a model/default, declaring arbitrary-notebook accuracy or inferring new V1 conversion
support. Previous v2 parameter-fidelity failures are not resolved by scores on different v3 tasks.

Preserve measured v3 fixtures as regressions. Further tuning on these observations would make
v3 development evidence, requiring another held-out dataset for claims. Harden Windows worker
cleanup and durable pre-execution capture, then evaluate independently reviewed complete notebooks:
step/grouping accuracy, node interfaces, pipeline wiring, source traceability and project-level
behavioral equivalence. Do not fine-tune or deploy broadly on the strength of these four tasks.
