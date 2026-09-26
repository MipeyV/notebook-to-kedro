# Node Code Benchmark

## Scope

`run_node_code_benchmark` evaluates a code provider over the reviewed deterministic planning
corpus, without executing notebooks or generated functions and without writing Kedro projects.
The initial corpus is `tests/fixtures/evaluation/planning/v1`: four synthetic notebooks and
26 tasks covering loading, preprocessing, splitting, scaling, training, prediction and metrics.
This is a development benchmark, not an estimate of performance on arbitrary user notebooks.

Before the first provider call, every notebook is loaded and statically analyzed. Its content
hash, task boundaries, source, interfaces, parameters and diagnostics must match the reviewed
planning fixture exactly. A stale fixture or incompatible plan aborts the entire benchmark
before any task source is sent to the model. Duplicate case IDs and empty corpora are rejected.

The benchmark holds the deterministic plan fixed to isolate code generation from semantic
grouping. The `semantic-v1` corpus has different reviewed boundaries and is not interchangeable
with this V1 code benchmark.

## Reference And Metrics

Each task's reference function is rendered in memory by the same `render_node_function` used
by the V1 generator. References are checked against the node-code contract before model calls.
The reference code is retained in the report but is **not sent to the provider**: the provider
receives only the ordinary `NodeCodeRequest` with original source and interface evidence.

Report schema version `1.0` records provider/model identity, the caller-supplied prompt version,
notebook hash, source-cell and statement provenance, request, raw response, parsed proposal,
reference function, diagnostic, and elapsed time for each task. It contains source code and
untrusted model output and may therefore contain secrets. Keep reports private unless reviewed;
never execute or import their contents automatically.

Each task has one status:

| Status | Meaning |
| --- | --- |
| `accepted` | Strict response parsing and static node-code validation passed. |
| `provider_error` | An expected `NodeCodeProviderError` occurred, such as a timeout. |
| `invalid_response` | The response violated the versioned JSON contract. |
| `invalid_code` | The parsed response failed identity or static Python checks. |

Expected failures are recorded and evaluation continues, with exactly one call per task and no
retry or fallback. Unexpected provider implementation errors propagate rather than being hidden
as model failures. Provider and model identity are captured before calls. Prompt provenance must
be supplied by the caller for the provider being evaluated; it is not inferred from its name.

The summary distinguishes:

- **Acceptance rate:** accepted tasks divided by all requested tasks, including failures.
- **V1 function AST match rate:** accepted functions whose AST exactly matches the V1 reference,
  divided by all requested tasks. Formatting and comments do not affect this comparison;
  docstrings, renamed locals, changed operations and changed parameter substitutions do.
- **Missing parameter reads:** among accepted tasks with parameters, the number with at least
  one parameter argument absent from AST name-load occurrences. The per-task report lists names.
- **Failure counts:** provider errors, invalid responses and invalid code, separately.
- **Duration:** per-task, total and mean time, including the provider call and static validation,
  excluding corpus preparation. Failed calls remain in the total and mean.

Rejected tasks have `null` AST-match and parameter-read results, not passing results. An AST
match concerns the function, not an independent review of imports or package versions. It is a
comparison against our V1 implementation, **not an independent ground truth or behavioral
equivalence proof**. A mismatch may be an equivalent rewrite or a bug and requires review.
Reading a parameter does not establish that it is used correctly or that it has not been
overwritten. A function can pass all static checks and still perform I/O or return wrong results.
The report explicitly sets `behavioral_equivalence` to `not_evaluated`.

## Local Run

With Ollama running locally and the chosen model already downloaded:

```python
from pathlib import Path

from notebook_to_kedro.evaluation import (
    load_planning_corpus,
    node_code_benchmark_to_dict,
    node_code_benchmark_to_json,
    run_node_code_benchmark,
)
from notebook_to_kedro.generation.code import NODE_CODE_PROMPT_VERSION, OllamaNodeCodeProvider

cases = load_planning_corpus("tests/fixtures/evaluation/planning/v1")
report = run_node_code_benchmark(
    cases,
    OllamaNodeCodeProvider("qwen3:8b", timeout_seconds=120),
    project_root=".",
    prompt_version=NODE_CODE_PROMPT_VERSION,
)
print(node_code_benchmark_to_dict(report)["summary"])
output = Path("generated/node-code-benchmark.json")
output.parent.mkdir(parents=True, exist_ok=True)
with output.open("x", encoding="utf-8") as stream:
    stream.write(node_code_benchmark_to_json(report))
```

Run from the repository root with the project environment. The model is an example, not an
accuracy recommendation. Each task is requested sequentially; a cold model load can dominate the
first timing. Temperature zero does not guarantee reproducible outputs. Record the model digest,
Ollama version, runtime and repository revision alongside reports when comparing repeated runs.

The API also accepts fake providers for deterministic offline tests. The ordinary test suite
does not call Ollama or require a model. Real-model runs are explicit local experiments.

## Initial Local Observation

One run on 2026-09-26 used `qwen3:8b` (Q4_K_M), Ollama `0.34.4`, Python `3.12.14`,
prompt `node-code-v1`, and the four V1 corpus notebooks. Model digest:
`500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
The benchmark was run from `feature/node-code-benchmark`, based on repository commit `2b0fcaa`.
No prompt or validator changes were made to improve scores during this run.

| Measure | Observed result |
| --- | --- |
| Tasks | 26 |
| Accepted by static validation | 23/26 (88.5%) |
| Exact V1 function AST matches | 19/26 (73.1%) |
| Provider / response-contract errors | 0 / 0 |
| Rejected code proposals | 3 |
| Accepted parameterized tasks missing parameter reads | 0/10 |
| Total / mean request-and-validation duration | 115.58 s / 4.45 s |

Review of the seven nonmatching or rejected proposals found:

- Three `train_model` proposals placed an import inside the function and were rejected.
- All four `evaluate_model` proposals omitted the standalone notebook expression `accuracy`.
  Two retained the assertion; two also removed `assert accuracy >= 0.90`, changing the failure
  behavior despite passing static validation.
- Two review notes incorrectly suggested that requiring accuracy >= 1.0 was invalid. Achieving
  exactly 1.0 is possible: generated review prose must not be treated as a reliable judgment.

The full local report is `generated/node-code-qwen3-8b-v1.json` (ignored by Git). These are single-
run development observations on a small synthetic corpus, not an accuracy guarantee. None of the
proposed functions were executed. The next improvement should target import placement and source
statement preservation, particularly assertions, while continuing to measure parameter fidelity.

## Next Validation Stage

Use the recorded mismatches to prioritize prompt or request-contract changes, especially exact
parameter substitution evidence. Subsequent work must introduce independent reviewed code
references, held-out notebooks, and isolated behavioral comparisons before claiming fidelity
or allowing model proposals to enter generated projects.
