# Local Body-Only Model Measurements

## Scope And Protocol

Six live runs recorded on 2026-10-06 measure the opt-in body-only path on the unchanged `v2`
development corpus: eight reviewed node requests and seventeen behavioral scenarios. Three
consecutive runs of `qwen3:8b` were followed by three of `qwen2.5-coder:7b` on the same machine.
All six artifacts were then replayed offline and compared with the
[body-only benchmark CLI](node-body-benchmark.md).

This is a node-generation experiment, not a complete-notebook conversion, a structure-planner
evaluation or a production accuracy estimate. These synthetic tasks have already informed prior
prompt experiments; they are development regressions, not fresh held-out evidence.

The fixed protocol used:

- Node corpus `tests/fixtures/evaluation/node_code/v2` and behavioral corpus
  `tests/fixtures/evaluation/behavioral/v2`, without changing references or scenarios.
- Repository revision `f334359a92a38609bc8a11bfc3bbb59ad1705872`, Python `3.12.14` on Windows,
  Ollama `0.35.1`, loopback endpoint `http://localhost:11434`.
- Prompt `node-body-v1`, body schema `1.0`, assembly `node-body-assembly-v1`, mandatory exact
  parameter evidence, and unchanged validator `node-code-validation-v4`.
- Local Q4_K_M models with the exact digests below; no model download or training.
- Existing transport: schema-constrained JSON, non-streaming requests, `think: false` and
  `temperature: 0`; no explicit random seed or context-length override.
- Provider timeout 120 seconds and `validated-local-subprocess-v1` execution with a ten-second
  timeout per scenario and default byte/capture limits.
- One proposal per node per live run, without retry, prompt tuning, repair or validator exceptions.
  Only statically accepted assemblies reach execution, with explicit consent.

| Model | Installed model digest |
| --- | --- |
| `qwen3:8b` | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |
| `qwen2.5-coder:7b` | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` |

The complete reviewed corpus SHA-256 is
`ce9d286d0fed3548d15ead5ae9ad9cedb4c9f50613c89ec6651d11c49f20c159`.
It was recomputed from the requests, approved references, negative controls, behavioral inputs,
expected results and comparators, and matched all twelve live/replay artifacts. Exact source
requests, notebook paths/hashes, versions and execution settings also agreed across live runs.

Ollama initially reported no loaded model. During each model's first run, `/api/ps` reported a
4096-token context and full VRAM residency. These snapshots are local observations, not pinned
benchmark settings or a permanent resource guarantee. The first run of each model includes loading;
all durations are retained rather than selecting the fastest run.

## Observed Results

| Model / run | Accepted nodes | End-to-end matches | Proposal phase | Execution |
| --- | --- | --- | --- | --- |
| `qwen3:8b` 1 | 7/8 (87.5%) | 16/17 (94.12%) | 56.37 s | 20.66 s |
| `qwen3:8b` 2 | 7/8 (87.5%) | 16/17 (94.12%) | 28.42 s | 14.27 s |
| `qwen3:8b` 3 | 7/8 (87.5%) | 16/17 (94.12%) | 28.61 s | 11.88 s |
| `qwen2.5-coder:7b` 1 | 8/8 (100%) | 17/17 (100%) | 49.76 s | 15.62 s |
| `qwen2.5-coder:7b` 2 | 8/8 (100%) | 17/17 (100%) | 27.76 s | 14.40 s |
| `qwen2.5-coder:7b` 3 | 8/8 (100%) | 17/17 (100%) | 27.61 s | 17.73 s |

Every evaluated scenario matched its reviewed expectation, including all five expected exceptions.
There were no provider errors, invalid response contracts, behavioral mismatches or execution errors.
Each `qwen3:8b` run had one statically rejected node and one not-evaluated scenario. The code model
had no rejected nodes or not-evaluated scenarios. The end-to-end denominator remains seventeen;
the evaluated-only 100% rate does not hide the general model's rejection.

The proposal phase includes prompt/provider work, parsing, assembly and static validation; it is
not pure inference latency. Execution includes subprocess setup rather than only function runtime.
Model loading, residency and background load affect timings; these observations do not establish
a production speed advantage.

| Node case | `qwen3:8b`, every run | `qwen2.5-coder:7b`, every run | Linked scenarios |
| --- | --- | --- | --- |
| `aggregate-orders` | Accepted, all matched | Accepted, all matched | 3 |
| `custom-ratio` | Accepted, all matched | Accepted, all matched | 2 |
| `date-features` | Accepted, all matched | Accepted, all matched | 3 |
| `encode-categories` | Accepted, all matched | Accepted, all matched | 3 |
| `evaluate-regression` | Accepted, matched | Accepted, matched | 1 |
| `fill-missing` | Rejected, not evaluated | Accepted, matched | 1 |
| `join-customers` | Accepted, all matched | Accepted, all matched | 3 |
| `split-holdout` | Accepted, matched | Accepted, matched | 1 |

Both models preserve the metric cell's final standalone `mae` expression. Deterministic assembly
supplies the terminal return, exact signature and necessary allowed module-level imports. Neither
model introduces the previously observed function-local split import in its accepted body.

The remaining `qwen3:8b` failure is exact parameter fidelity: its imputation body repeats the raw
literal dictionary instead of substituting the planned `missing_values` argument. The code model
proposes `clean = frame.fillna(value=missing_values)` as required. The unchanged AST validator
rejects the former before execution. It is not an observed runtime mismatch, and no repair was
applied to make it pass. Runtime equivalence of that rejected body remains unmeasured.

## Stability And Offline Replay

Within each model, all eight raw assistant JSON strings and parsed bodies were identical across
three live runs, including review notes. All accepted assembled responses were also identical:
seven for `qwen3:8b`, eight for the code model. This is observed repeatability under this setup,
not a guarantee from temperature zero or eight new independent tasks on every run.

| Replay | Accepted nodes | End-to-end matches | Execution |
| --- | --- | --- | --- |
| `qwen3:8b` 1 | 7/8 | 16/17 | 17.82 s |
| `qwen3:8b` 2 | 7/8 | 16/17 | 18.45 s |
| `qwen3:8b` 3 | 7/8 | 16/17 | 18.56 s |
| `qwen2.5-coder:7b` 1 | 8/8 | 17/17 | 19.44 s |
| `qwen2.5-coder:7b` 2 | 8/8 | 17/17 | 19.63 s |
| `qwen2.5-coder:7b` 3 | 8/8 | 17/17 | 19.54 s |

Every replay used the original raw bodies, reassembled and validated them, then re-executed
accepted proposals without Ollama. Raw responses, parsed bodies, assembled responses, statuses,
non-timing summary metrics and every per-scenario comparison matched the source live artifact.
Each replay records its complete source-envelope SHA-256. Provider duration is zero by definition;
live/replay comparisons correctly emit a null provider-time delta and mark it non-comparable.

Thirteen comparison files were generated: four within-model repeated-run comparisons, six
live/replay comparisons and three paired between-model comparisons. The first ten have unchanged
proposal and evaluated-scenario statuses. Each between-model comparison improves only
`fill-missing` and `fill-missing-standard`, with zero regressions: +12.5 percentage points in node
acceptance and approximately +5.88 points in end-to-end matching for the code model.

## Historical Context, Not A Controlled Format Ablation

| Model | Historical full-code `v4`, every run | Current body-only, every run |
| --- | --- | --- |
| `qwen3:8b` | 6/8 nodes, 15/17 matches | 7/8 nodes, 16/17 matches |
| `qwen2.5-coder:7b` | 7/8 nodes, 16/17 matches | 8/8 nodes, 17/17 matches |

The historical [full-code baseline](behavioral-code-benchmark.md#expanded-dataset-baseline) and
[code-model comparison](local-code-model-comparison.md) used Ollama `0.35.0`, not `0.35.1`.
Local artifact inspection confirmed identical requests, notebook paths/hashes, provider/execution
configuration and validator versions. Git inspection also confirmed unchanged `v2` corpora,
source fixtures, dependency lockfile and validator source since the baseline revision.

Nevertheless, the runtime, prompt and response/assembly path differ. The table is descriptive
historical context, not a causal estimate of deterministic assembly's contribution or an automated
mixed-format comparison. The body comparator intentionally rejects legacy full-code envelopes,
which lack complete corpus identity. A corpus-bound bridge and contemporaneous full-code controls
under the same runtime are needed for a controlled format ablation.

For the general model, the historical metric and split failures disappear, but imputation now
fails despite passing historically. This is a cross-task regression, not an unqualified success.
For the code model, all existing development cases now pass without changing the strict validator.

## Local Evidence And Reproduction

Raw responses remain private in ignored `generated/`, not in this documentation commit. The
filename stem is `node-body-{model}-v2-20261006-run-{n}`, where `model` is `qwen3-8b` or
`qwen25-coder-7b`, and `n` is 1, 2 or 3. Append `.json` for live artifacts or `-replay.json` for
replays. Canonical hashes below identify whole envelopes, not only embedded reports or file bytes.

| Model / artifact | Canonical envelope SHA-256 |
| --- | --- |
| `qwen3-8b` live 1 | `f928fd8821f62e1e4b9f5411ed4c8c335467d1829594d10fd28182ef164b2c9d` |
| `qwen3-8b` live 2 | `d6305d3ebc78169768764e3e1d355bbca47c0c08401d37522b92d4040025dba0` |
| `qwen3-8b` live 3 | `d3796f2c49a153d13f882253cea445da8ced7c77cf333d288612081bda03ee7f` |
| `qwen3-8b` replay 1 | `cdb8599adbd07d5df3b77eeb7af313a9c6e7071995fb91dc52c65c317819366a` |
| `qwen3-8b` replay 2 | `623e8a594900b0a7d10a4f31ef4af25ec7e1582941b80f1bed7a73d6a0191109` |
| `qwen3-8b` replay 3 | `c1b0f1b76e847dd727f2dddfe04ba4e9ed7ddb541615050a06a7f487069cfee9` |
| `qwen25-coder-7b` live 1 | `2e8c0d88538c0aa6e322b4d67efc730c8868fe1494c7776f037f306d55c5e902` |
| `qwen25-coder-7b` live 2 | `0eab96331c1fe2e06c9c881e3d532d04232e76e964aea11b938f8d23fe3e11b5` |
| `qwen25-coder-7b` live 3 | `03aa05c36c265d9322b7473cfbd3ca75fe1fa0540e6d382602a5d80306f6a6e0` |
| `qwen25-coder-7b` replay 1 | `b77023bfee253a0d14b97179917c258968a5000671b3de332b2385adc448b694` |
| `qwen25-coder-7b` replay 2 | `d050b0bfb49918e1904d6fb4aa5dceefae44858cfb3f3f253105296ca34bbbb5` |
| `qwen25-coder-7b` replay 3 | `a37c29bb57e629c12c44860fdd8a6e4894f1a007e24c9407d6bc7483e49253d2` |

Within-model comparisons append `-vs-2.json` or `-vs-3.json` to the run-1 stem. Each live/replay
comparison appends `-vs-replay.json` to its live stem. Between-model comparison filenames are
`node-body-qwen3-vs-qwen25-coder-v2-20261006-run-{n}.json`.

Follow the [run/replay/compare commands](node-body-benchmark.md#cli) with these same corpus,
model and timeout settings, repeated three times per model. Use fresh output stems: the atomic
writer refuses overwrite. No model download is necessary when these digests are already installed.
New timestamps and durations change artifact hashes even when code and outcomes are identical.
These local evidence files are not distributed with the repository; published hashes are not a
substitute for access to raw artifacts or independent reproduction.

## Decision And Next Step

Keep `qwen2.5-coder:7b` plus body-only assembly as the stronger candidate for the next pilot, not
an application default or a trained model. Production code, prompts, validation, reviewed corpora
and deterministic conversion defaults are unchanged by this experiment. Accepted proposals do not
automatically enter generated Kedro projects.

Add fresh, independently reviewed task patterns before claiming generalization, and keep the
observed imputation failure as a development regression. Add a corpus-bound cross-format bridge
and fresh full-code controls before attributing historical score changes to the new path. Entire
notebooks, project-level runtime equivalence and the structure-planner role still need separate
evaluation. Subprocess execution is fault containment, not an OS security sandbox.
