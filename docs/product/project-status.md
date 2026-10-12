# Detailed project status

[Documentation index](../README.md)

Status: implementation and measurement snapshot, extracted on 2026-10-11.
Historical measurements retain their original corpus, runtime and limitations.

## Project status

A [draft complete-notebook pilot](../evaluation/synthetic-notebook-pilot.md) now checks a
seeded simulation and real local CSV catalog loading through nine generated nodes, with
explicit intermediate/output expectations and six negative controls. Independent human review
is pending; this is deterministic development evidence, not a whole-notebook LLM measurement.
Its test-only CSV connector changes the locked pandas runtime, as recorded in the pilot report.
The [human review worksheet](../evaluation/synthetic-pilot-review.md) and
[whole-notebook experiment proposal](../evaluation/whole-notebook-experiment.md) are now documented.
They do not approve the fixture, implement a live runner or measure a model; the proposed first
experiment holds source interpretation and task boundaries fixed to evaluate code proposals.
An [offline static batch API](../evaluation/offline-notebook-body-batch.md) now prepares and
validates all recorded bodies without provider or execution I/O. Trusted fixed bodies match the
complete pilot in tests; live measurement remains pending.
The [draft source-binding wrapper](../evaluation/notebook-source-binding.md) now rechecks exact
local file identities and deterministic reconstruction before response validation. It preserves
pending review and adds neither approval, artifact persistence nor live execution.
A separate [draft capture API](../evaluation/notebook-body-capture.md) now persists that binding,
request reservations and raw outcomes, verifies missing/unfinished inventory, and replays static
validation offline. It does not contact a provider, execute proposals or approve the draft.
A separate [draft pipeline worker](../evaluation/notebook-pipeline-worker.md) now requires renewed
execution consent, copies verified source bytes into a private evaluation project, runs the complete
DAG in a fresh process and returns typed JSON observations for explicit comparison. Trusted fixtures
match seventeen observables against the notebook and hand expectations; no model accuracy, human
approval or OS sandbox is claimed.
A separate [draft artifact API](../evaluation/notebook-pipeline-artifacts.md) now publishes complete
execution/comparison evidence exclusively, records selected local runtime controls before/after,
inspects reports without execution and requires compatible controls plus renewed consent for replay.
Unknown identities and observed drift block replay. A separate [human review evidence API](../evaluation/notebook-human-review.md)
now prepares unchecked requests, binds externally supplied declarations/proof bytes to the complete
reference and validates explicit operator-accepted wrappers. It authenticates neither identity nor
independence; the actual fixture still has no recorded independent human approval. Actual review,
durable execution attempt accounting, verified model controls and live collection remain outstanding.

The deterministic V1 pipeline is operational for the supported notebook subset. It can analyze a notebook, build and validate a reviewable conversion plan, render a Markdown report, and generate a minimal Kedro project whose observable outputs are checked against reference notebooks.

Development is now moving from the deterministic foundation toward V2 hybrid semantic planning and broader notebook coverage. The deterministic path will remain available as the default and as the fallback for every future provider integration.

The [node code generation API](../reference/node-code-contract.md) provides versioned task requests,
strict JSON responses, a fake provider for offline tests, and an opt-in local Ollama code provider
with a versioned fidelity prompt. Function signatures, imports, global references, and returns
are statically validated, with versioned guards against changed or missing assertion blocks and
incorrect parameter substitutions. All node bodies, with or without parameters, must preserve the
source AST except for the exact planned substitutions and the required terminal return. Deleted,
added or rewritten instructions are rejected, even for potentially equivalent refactorings.
A [node code benchmark](../evaluation/node-code-benchmark.md) measures acceptance,
V1 function AST matches, missing parameter reads, failures and latency over 26 tasks in four
reviewed notebooks. Accepted proposals are never written into generated projects automatically.
An explicit evaluation API can execute them after static validation and caller consent;
behavioral results remain distinct from static benchmark scores.

An [independent node-code corpus](../evaluation/node-code-evaluation-corpus.md) now contains eight notebook
tasks with hand-authored references and seventeen known-invalid proposals. The expanded `v2`
dataset preserves the four-case `v1` baseline and adds aggregation, joins, categorical encoding and
calendar features. It measures compilation,
static validation, AST fidelity, detected errors and false rejections without using the V1 generator
as ground truth or calling a model. This remains a small synthetic validator corpus, not an accuracy
claim or behavioral-equivalence result.

A versioned [behavioral comparison contract](../reference/behavioral-comparison-contract.md) now links seventeen
reviewed runtime scenarios to that independent corpus. It represents finite scalars, nested JSON,
typed arrays and tables, plus exact, numeric, array and table comparison policies or expected
exceptions. Approved reference functions now run in isolated Python subprocesses with temporary
working directories, filtered environments, timeouts and bounded transport. Deterministic
comparators produce per-output diagnostics and aggregate reports; all seventeen reference scenarios
match their reviewed expectations. Statically valid proposals can now be executed through an
explicit opt-in subprocess path and compared with an auditable response hash. This is fault
containment rather than an OS sandbox. A
[behavioral code benchmark](../evaluation/behavioral-code-benchmark.md) now measures real provider outputs
without dropping rejected nodes. The first local `qwen3:8b` run accepted 2/4 nodes and matched 3/5
reviewed scenarios end to end; this small single run is not a general accuracy claim. Versioned
benchmark artifacts now preserve raw responses, model and runtime provenance, configuration and
integrity hashes. They can be replayed without Ollama and compared for static, behavioral and
latency regressions through the CLI. A three-run `qwen3:8b` baseline reproduced the same 2/4 static
acceptance and 3/5 end-to-end matches every time; the corpus is still too small for a general
accuracy claim.
The measured 60% result applies to the frozen `v1` dataset. Three unchanged `qwen3:8b` runs on the
expanded `v2` dataset each accepted 6/8 nodes (75%) and matched 15/17 scenarios end to end (88.24%);
an offline replay reproduced the same outcomes. All four new tasks passed all twelve linked
scenarios, while the same two original nodes remained statically rejected. The higher percentage
reflects the added passing cases, not a model improvement; these synthetic task-cell measurements
do not establish full-notebook conversion accuracy.

A [controlled local code-model comparison](../experiments/local-code-model-comparison.md) kept the same
`v2` inputs, prompt and validator. Three `qwen2.5-coder:7b` runs and an offline replay each accepted
7/8 nodes and matched 16/17 scenarios (94.12%). The split node improved without observed regressions;
the source-expression omission remained rejected. This is a pilot-model signal, not a general
accuracy claim, a fine-tuned model or an automatic change to conversion defaults.

A later [statement-retention prompt experiment](../experiments/node-code-statement-retention.md) retained the
omitted metric expression but regressed other tasks on both models. The `v5` candidate was rejected;
active prompts remain default `v1` and opt-in `v4`, with the strict validator unchanged. Current
measured `v4` results therefore remain 15/17 for `qwen3:8b` and 16/17 for `qwen2.5-coder:7b`.

A separate [node body contract](../reference/node-body-contract.md) now provides an offline Python API
for proposing only body statements. Deterministic AST assembly supplies the exact signature,
necessary permitted imports and terminal return, then applies the unchanged strict validator.
It does not repair omissions or execute proposals. All eight approved reference bodies assemble
correctly and match seventeen scenarios with explicit test consent; this is not a model-accuracy
measurement. An opt-in [body-only Ollama provider](../guides/ollama-node-body.md) now exposes
`request_node_body`, with mandatory parameter evidence, strict assembly and exact raw-response
provenance. A separate [body-only benchmark/replay API and CLI](../evaluation/node-body-benchmark.md) archives
all proposals and replays their raw bodies without Ollama on an integrity-bound corpus.
Approved-reference benchmark and replay match all seventeen scenarios; this does not establish
live model accuracy. `behavioral-benchmark run|replay|compare --proposal-format node-body`
explicitly selects body artifacts; comparison checks corpus/source and execution compatibility,
retains rejected denominators and does not treat replay as live latency.
[Three live body-only runs per model and their offline replays](../experiments/node-body-local-measurements.md)
now reproduce 7/8 accepted nodes and 16/17 matches for `qwen3:8b`, and 8/8 and 17/17 for
`qwen2.5-coder:7b`. The former systematically misses one parameter substitution; the latter passes
this small synthetic development corpus, not arbitrary notebooks. Fresh independent tasks remain
necessary. A [corpus-bound format comparison](../evaluation/generation-format-comparison.md) now archives
complete full-code corpus evidence with `--proposal-format bound-full-code` and compares it to
body mode using `behavioral-benchmark compare-formats`. Exact corpus/runtime controls are required;
legacy measurements cannot be upgraded retroactively and used a different Ollama version.
Conversion defaults are unchanged.

A separate [`v3` corpus](../evaluation/fresh-node-corpus-v3.md) adds tasks beyond the earlier development cases:
four disjoint task contracts, twelve scenarios and eight negative controls for imported helpers,
Unicode normalization, branching, stateful loops and multiple outputs.
[Twelve complete same-runtime model runs and their replays](../experiments/fresh-v3-format-measurements.md)
now show 4/4 nodes and 12/12 matches for `qwen3:8b` in both formats and for
`qwen2.5-coder:7b` in body mode. The code model's full-code path consistently omits an assertion,
is rejected before execution and retains 3/4 nodes and 9/12 matches. The report preserves an
initial Windows infrastructure interruption, exact evidence and small-sample limits.
This is not whole-notebook accuracy; prompts, validation and conversion defaults are unchanged.

The [behavioral executor](../evaluation/behavioral-code-benchmark.md#local-run) now bounds Windows
permission-error cleanup retries and logs persistent failures without discarding worker outcomes.
This does not retry model calls or execution. Optional [durable response capture](../guides/response-capture.md)
now publishes raw outcomes before validation/execution with `--capture-dir`, exposes `capture-info`,
and recovers complete captures without Ollama using `behavioral-benchmark recover`. Partial evidence
cannot masquerade as a completed benchmark. Independent review of the draft whole-notebook
pilot remains the next gate before a model-assisted project experiment.

An opt-in provider mode supplies [exact parameter substitutions](../reference/node-parameter-evidence.md):
original expressions, literal types, source ranges and corresponding function arguments derived
from V1 rules. Ambiguous mappings fail before model I/O in this experimental mode. The static validator
independently checks these substitutions for every provider; it does not prove runtime equivalence.

The initial deterministic analysis contract is documented in [docs/reference/mvp-contract.md](../reference/mvp-contract.md), and its interchange model is defined in [docs/reference/notebook-facts-schema.md](../reference/notebook-facts-schema.md).

The first reference fixture runs a deterministic Iris classification workflow. It provides a known-good baseline whose predictions and accuracy can later be compared with the generated Kedro pipeline.

The planned module boundaries and test strategy are described in [docs/reference/architecture.md](../reference/architecture.md). Supported runtimes and library-support levels are defined in [docs/reference/compatibility.md](../reference/compatibility.md).

The first versioned IR is implemented as immutable Python models with deterministic dictionary and JSON round trips:

```python
json_text = facts.to_json()
restored = NotebookFacts.from_json(json_text)
```

The notebook loader now validates local Jupyter notebooks, rejects unsupported formats and non-Python notebooks with stable diagnostic codes, and returns normalized source cells without executing or analyzing notebook code.

The analyzer extracts imports, top-level statements, reads, writes, calls, and blocking syntax diagnostics from loaded notebooks. It resolves cross-cell dependencies by linking reads to the most recent earlier data definition.

The package now exposes a public analysis entrypoint that loads a notebook path and returns deterministic `NotebookFacts`:

```python
from notebook_to_kedro import analyze_notebook_path

facts = analyze_notebook_path("notebooks/model.ipynb")
```

It also exposes a planning entrypoint that proposes Kedro-oriented task candidates without writing
project files. Deterministic planning is the default:

```python
from notebook_to_kedro import plan_notebook_path

plan = plan_notebook_path("notebooks/model.ipynb")
```

Hybrid planning must be selected explicitly and requires a downloaded local Ollama model:

```python
from notebook_to_kedro import PlannerMode, plan_notebook_path

plan = plan_notebook_path(
    "notebooks/model.ipynb",
    planner=PlannerMode.HYBRID,
    ollama_model="your-local-model",
)
```

`create_semantic_planner` can be used separately when an application wants to construct and reuse
a planner. A custom object implementing `SemanticPlanner` can still be injected directly.

The package can render a deterministic Markdown report from a plan so reviewers can inspect the proposed nodes, catalog datasets, parameters, and blocking diagnostics before generation:

```python
from notebook_to_kedro import render_conversion_report

report = render_conversion_report(plan)
```

Plans can also be validated explicitly before generation:

```python
from notebook_to_kedro import validate_conversion_plan

validate_conversion_plan(plan)
```

The same static review flow is available from the command line:

```bash
notebook-to-kedro plan notebooks/model.ipynb
```

After reviewing the plan, the CLI can generate the minimal Kedro project:

```bash
notebook-to-kedro generate notebooks/model.ipynb generated/model_project
```

Expected notebook loading and generation failures are reported as concise CLI errors on stderr with a non-zero exit code.

The first Kedro generator writes an importable minimal project skeleton from a `ConversionPlan`:

```python
from notebook_to_kedro import generate_kedro_project

generate_kedro_project(plan, "generated/model_project")
```

The end-to-end suite now executes the generated Kedro pipeline for the reference Iris notebook and compares its final accuracy with the notebook output.

The planner recognizes simple `pd.read_csv("...")` assignments as catalog inputs. The generator writes a minimal `conf/base/catalog.yml` for those CSV-backed datasets and copies the source CSV into the generated project's `data/01_raw/` directory.

The planner also extracts selected literal scikit-learn parameters, and the generator writes `conf/base/parameters.yml` while wiring nodes with Kedro `params:` inputs.

Generated node names are now deterministic but reviewable: the planner uses nearby Markdown headings when available and falls back to simple source patterns such as `split_data`, `train_model`, `predict`, and `evaluate_model`.

The supported scikit-learn workflow now includes a simple `StandardScaler` preprocessing step using `fit_transform` and `transform`, with literal `with_mean` and `with_std` parameters extracted into Kedro configuration.

The planner recognizes simple pandas preprocessing steps such as `dropna`, `fillna`, and `assign` when they rewrite a dataframe variable, producing reviewable node names like `clean_data`, `impute_missing_values`, and `engineer_features`.

The planner also extracts selected literal pandas preprocessing parameters into Kedro configuration, including `fillna(value=...)`, positional `fillna({...})`, and `drop(columns=[...])`.

The planner also emits conversion diagnostics for review risks such as fallback names, inherited cell diagnostics, unresolved external inputs, and tasks without data outputs. These diagnostics are visible in the Markdown report and do not block generation unless the plan itself has blocking diagnostics.

Progress and architectural decisions are recorded chronologically in [JOURNAL.md](../../JOURNAL.md).
