# Development Journal

This file provides a chronological record of **Notebook to Kedro** development.

It keeps track of:

- work that has actually been completed;
- architectural decisions and their rationale;
- limitations discovered along the way;
- unresolved questions;
- the next concrete step.

This journal is neither a release changelog nor a simple backlog. An entry is added when work is completed or a structural decision is made.

## Entry convention

New entries should follow this structure whenever possible:

```markdown
## YYYY-MM-DD — Short title

### Completed

- ...

### Decisions

- ...

### Open questions

- ...

### Next step

- ...
```

The newest entries are added at the top, immediately below this convention, so the current state remains easy to find.

---

## 2026-10-07 - Fresh standalone node corpus v3

### Completed

- Added four disjoint task notebooks and independent hand-authored node contracts in `v3`, with
  twelve scenarios, four expected exceptions, eighteen output records and eight invalid variants.
- Covered a stdlib helper/list comprehension, Unicode case folding, inclusive conditional
  partitioning, stateful transactions with `continue`/raise and multi-output tied table ranking.
- Kept `v1`/`v2` measured fixtures, schemas, prompts, production code and validator unchanged.
- Pinned full corpus identity and tested source provenance, notebook validity, empty execution
  state, ordered interfaces, body/reference AST assembly and disjoint prior identities/sources.
- Detected every fixed negative control statically and through the intended behavioral scenario.
- Executed all twelve references and validated proposals in real subprocesses, then benchmarked
  reference bodies and replayed their raw responses offline; no Ollama model was invoked.
- Documented fixture eligibility versus independent human sign-off: maintainer PR review is
  required before first scored evaluation. These candidates are synthetic task snippets, not
  complete notebooks or a new model-accuracy claim.
- Passed 1,071 full-suite tests on Python `3.12.14` and 1,043 deterministic tests on each of
  `3.11.16` and `3.13.14`, all with 100% line/branch coverage. Ruff lint/format and strict mypy
  passed; the Windows mypy launcher was blocked, so its Python module entry point was used
  without modifying application-control policy.
- Built both distributions, verified the pinned corpus identity and documentation links, and
  restored the locked development environment to Python `3.12.14`.

### Decisions

- Keep this dataset separate rather than mixing the fresh cases into the tuned development corpus.
- Freeze candidate identity before model observation; preserve future measured revisions.
- Use only existing supported scopes. Nested helpers remain rejected rather than weakening
  validation to admit them. Imported stdlib helpers exercise the existing allowed-import boundary.

### Open questions

- How will both local models perform on these new cases without prompt changes?
- Which independently reviewed real notebooks and additional supported task patterns should follow?

### Next step

- Review and merge the candidate dataset, then add corpus-bound cross-format comparison and
  same-runtime controls before scored evaluation. Full notebook and project equivalence remain.

## 2026-10-06 - Repeated local body-only model measurements

### Completed

- Recorded three live `qwen3:8b` runs followed by three `qwen2.5-coder:7b` runs on the unchanged
  eight-node, seventeen-scenario `v2` development corpus at revision `f334359`.
- Captured Ollama `0.35.1`, Python `3.12.14`, full model digests, exact corpus identity and
  unchanged `node-body-v1` prompt / `node-code-validation-v4` validation with parameter evidence.
- Observed stable 7/8 accepted nodes and 16/17 matches for the general model, and 8/8 and 17/17
  for the code model, with no provider errors, invalid responses, mismatches or execution errors.
- Inspected the general model's imputation rejection: a retained literal instead of the exact
  planned parameter argument. No retry, output repair or validator exception was applied.
- Replayed all six artifacts offline; verified raw/parsed/assembled responses, non-timing
  summaries and per-scenario comparisons against their live source envelopes.
- Created thirteen body comparisons: stable intra-model and live/replay outcomes, plus one improved
  node/scenario for the code model in each paired cross-model comparison with zero regressions.
- Confirmed byte-identical raw responses within each model across three runs. Retained every
  duration, whole artifact hash and the rejected scenario's full denominator in the report.
- Checked historical requests/source identities/configuration and unchanged corpus, lockfile and
  validator content; documented the historical Ollama `0.35.0` versus current `0.35.1` caveat.
- Kept raw artifacts private in ignored `generated/`; changed documentation only.
- Passed 1,038 deterministic tests on Python `3.12.14` with 100% line/branch coverage, Ruff
  lint/format, strict mypy and distribution builds. The full multi-version test suite was not
  rerun for this documentation-only change.
- Verified every published model/corpus/artifact hash, all eighteen rounded durations and local
  report links directly against the recorded evidence.

### Decisions

- Prefer the code model plus body-only assembly for further evaluation, not as a new default.
- Treat these previously inspected synthetic tasks as development regressions, not fresh held-out
  evidence, whole-notebook accuracy or a causal format ablation.
- Keep runtime validation strict and make no silent repairs or project-generation integration.

### Open questions

- Will the candidate remain faithful on fresh task patterns and independently reviewed notebooks?
- Will contemporaneous full-code controls reproduce the historical format differences?

### Next step

- Add independent tasks and a corpus-bound full-code/body-only bridge with same-runtime controls
  before broader accuracy claims or promotion. Full notebook and structure-planner evaluation remain.

## 2026-10-06 - Body-only benchmark CLI and compatible comparison

### Completed

- Added explicit `--proposal-format node-body` selection to behavioral benchmark run/replay/compare.
- Kept full-code CLI defaults, artifact formats, prompts, validation and conversion unchanged.
- Made exact parameter evidence mandatory in body runs and retained renewed execution consent.
- Added a body comparison API with envelope revalidation, corpus/source identity, compatible
  validation/execution contracts, outer artifact hashes, full summaries and rejection diagnostics.
- Recorded both model/prompt/environment/configuration metadata; replay provider timing is
  non-comparable to live timing and its delta is null.
- Added offline CLI orchestration, real artifact roundtrips, format isolation, consent, exclusive
  output and compatibility regression tests without model calls.
- Passed 1,056 tests on Python `3.12.14` and 1,038 deterministic tests on each of `3.11.16` and
  `3.13.14`, all with 100% line and branch coverage (5,279 statements and 1,504 branches).
- Passed Ruff lint/format, strict mypy and distribution builds.

### Decisions

- Require explicit artifact format instead of inferring it from untrusted files.
- Compare only body artifacts in this increment. Legacy full-code artifacts lack complete corpus
  identity; case-name equality is insufficient for safe automated cross-format conclusions.
- Keep metrics over all proposals/scenarios, including rejected and not-evaluated outcomes.

### Open questions

- Will body-only prompting improve acceptance and behavioral match rates for either local model?
- What corpus-bound evidence should accompany historical full-code runs for cross-format comparison?

### Next step

- Measure both local models on the unchanged eight-node, seventeen-scenario corpus, archive raw
  bodies, replay offline and compare repeated runs; no body-only accuracy improvement is claimed yet.

## 2026-10-04 - Body-only benchmark artifacts and offline replay

### Completed

- Added `run_node_body_benchmark` and an explicit body-only artifact envelope, schema `1.0`.
- Reused behavioral metric serialization and factored the existing accepted-proposal evaluation
  helper without changing full-code reports, artifacts, prompts or conversion defaults.
- Preserved exact raw responses and parsed bodies, including static rejections, while exposing
  assembled code and evaluations only for accepted proposals.
- Recorded body, assembly, evidence, prompt and validator versions with source and corpus identities.
- Added duplicate-key rejection, raw/parsed/assembled consistency checks, mutation detection and
  exclusive atomic writes using existing artifact helpers.
- Added replay without provider/network calls, requiring supported versions, the exact corpus,
  matching recorded sources and renewed execution consent. Replay proposal durations are zero.
- Executed and replayed all seventeen scenarios for the eight approved reference nodes in real
  subprocesses. These are compatibility results, not new model-accuracy measurements.
- Passed 1,036 tests on Python `3.12.14` and 1,018 deterministic tests on each of `3.11.16` and
  `3.13.14`, all with 100% line and branch coverage. The previously observed Windows pandas DLL
  failure did not recur on this Python 3.11 run; no security policy or tests were changed to bypass it.
- Passed Ruff lint/format checks, strict mypy and distribution builds; restored the locked
  development environment to Python `3.12.14`.

### Decisions

- Keep body-only artifacts explicitly separate from full-code artifacts; do not silently relabel
  raw body responses as complete model-generated functions.
- Bind replay to all reviewed corpus content, not only successful scenario IDs or node names.
- Preserve rejected proposals without synthesizing repair code or dropping their denominators.
- Scope this PR to the Python API and artifact/replay boundary, with no live model calls or CLI changes.

### Open questions

- How should comparisons label the structural change from full-code proposals to deterministic assembly?
- Will body-only prompting improve the measured acceptance of the two local models?

### Next step

- Add explicit body-only CLI run/replay and compatible artifact comparison, then capture controlled
  local measurements for both models on the unchanged eight-node, seventeen-scenario corpus.

## 2026-10-04 - Opt-in Ollama body-only provider and service

### Completed

- Added a separate local `OllamaNodeBodyProvider` using the existing bounded chat transport.
- Added prompt `node-body-v1`, always supplying exact parameter evidence and preserving raw
  source as untrusted JSON data without function-shell examples.
- Added provider-neutral `NodeBodyProvider`, `request_node_body` and immutable `NodeBodyResult`.
- Retained exact raw assistant JSON, parsed body, assembled full-code response and application-owned
  provider, model, prompt and assembly versions for accepted proposals.
- Added simulated transport checks for all eight reviewed reference bodies, schema separation,
  lazy construction, error boundaries, preflight failures and absence of execution.
- Pinned the new prompt digest without changing the existing full-code prompt digests.
- Passed 990 tests on Python `3.12.14` and 973 deterministic tests on `3.13.14`, both with 100%
  line and branch coverage, plus Ruff, mypy and distribution builds.
- On Python `3.11.16`, 969 deterministic tests passed, including every new test. The same four
  existing worker tests failed because Windows application control blocked pandas' `indexing`
  DLL; the Linux CI check remains required. No tests or coverage requirements were weakened.

### Decisions

- Keep this integration opt-in through the Python API, with no CLI/default changes or live calls.
- Require exact parameter evidence before provider I/O; do not provide a weaker body-only mode.
- Preserve strict validation, execution consent and the prohibition on automatic proposal writing.
- Build this branch on the body-contract branch while its merge into `main` remains pending.

### Open questions

- Does this body-only mode improve model acceptance without cross-task regressions?
- How should benchmark artifacts retain both raw body and assembled response for rejected cases?

### Next step

- Add a versioned body-only benchmark/replay adapter and then measure both local models on the
  unchanged corpus, with explicit behavioral-execution consent and complete provenance.

## 2026-10-04 - Body-only contract and deterministic function assembly

### Completed

- Added immutable `NodeBodyResponse` schema `1.0`, with exact JSON fields and separate schema export.
- Added `assemble_node_body` and version `node-body-assembly-v1`, producing a compatible
  `NodeCodeResponse` from the trusted request interface and an untrusted body.
- Selected only referenced allowed imports in request order and appended the exact output return.
- Used AST assembly to preserve multiline string values without textual-indentation changes.
- Added offline fidelity, identity, import, parameter and non-execution regressions, plus checks
  against eight reviewed reference bodies and seventeen consent-gated behavioral scenarios.
- Passed 952 tests on Python `3.12.14` and 935 deterministic tests on `3.13.14`, both with
  100% line and branch coverage, plus Ruff, mypy and distribution builds.
- On Python `3.11.16`, 931 deterministic tests passed, including all new body tests; four existing
  worker tests failed because Windows application control blocked pandas' `indexing` DLL.
  A retry reproduced the environment failure; the Linux CI check remains required.

### Decisions

- Keep the existing full-code provider mode, prompts and validator unchanged.
- Do not repair bodies, insert missing statements, strip unwanted statements or substitute literals.
- Treat reference compatibility separately from model accuracy. No live model was called this step.
- Preserve execution consent and keep accepted proposals out of automatic project generation.

### Open questions

- Will a body-only local prompt improve end-to-end acceptance without cross-task regressions?
- Which fresh independent tasks should be added before assessing generalization?

### Next step

- Add an explicit local body-only provider and prompt, then a versioned benchmark/replay adapter
  recording raw bodies, assembled responses and assembly provenance before comparing both models.

## 2026-10-03 - Statement-retention prompt rejected after cross-task regressions

### Completed

- Tested generic source-statement retention instructions and assembly examples without changing
  source requests, parameter derivation, schemas, corpus references or validator policy.
- Archived the complete `node-code-v5` candidate at clean revision
  `f5252ce230f92137328f1058d8fbe934d418c9e6` before capturing one live run per local model.
- Evaluated the same eight nodes and seventeen scenarios with the existing model digests,
  Ollama `0.35.0`, Python `3.12.14` and validator `node-code-validation-v4`.
- Observed 6/8 accepted nodes and 13/17 matches for `qwen3:8b`, versus 6/8 and 15/17 on `v4`.
  The code model accepted 3/8 and matched 6/17, versus 7/8 and 16/17 on `v4`.
- Confirmed the metric node retains its final expression and matches its reviewed scenario on
  both models, but other proposals add source-absent expressions, lose parameter arguments or
  put imports outside the requested function structure.
- Compared each candidate with its `v4` baseline and replayed both offline. Replays reproduced
  the same statuses; the validator blocked every rejected proposal before execution.
- Restored production code exactly to `main`: active prompts remain default `v1` and opt-in `v4`.
- Added pinned fixture digests for both active prompts and six source-data regression cases for
  standalone expressions, calls and assertions without invoking a provider.
- Passed 886 tests on Python `3.12.14` and 870 deterministic tests on each of Python `3.11.16` and
  `3.13.14`, all with 100% line and branch coverage, plus Ruff, mypy and distribution builds.

### Decisions

- Do not promote a prompt based on one corrected task when other reviewed tasks regress.
- Preserve the archived candidate revision and private raw artifacts, but keep only aggregate
  reviewable evidence in documentation. Uncommitted exploratory drafts are not reproducible baselines.
- Stop the candidate experiment after observed regressions rather than claim three-run stability.
- Treat the inspected corpus as development regressions for later prompt work; new generalization
  measurements require fresh independently reviewed cases.
- Keep strict validation and avoid silent repair or execution of rejected code.

### Open questions

- Can a deterministic function shell eliminate structural failures while leaving useful source-body
  reasoning to the model under an explicit contract?
- What fresh task families and complete notebooks should validate that approach?

### Next step

- Specify and test a versioned source-body proposal contract with deterministic signature, import
  boundaries and terminal-return assembly, retaining validation and explicit execution consent.

## 2026-10-02 - Local code model improves split fidelity without validator changes

### Completed

- Installed `qwen2.5-coder:7b` locally in Ollama, verifying Q4_K_M model digest
  `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`.
- Captured three live candidate artifacts at revision `0a259927d0db954fdadb4b9d4d1b18afc29543f3`
  using Ollama `0.35.0`, Python `3.12.14`, prompt `node-code-v4` and validator
  `node-code-validation-v4`, then replayed the first artifact without model calls.
- Reproduced 7/8 accepted nodes and 16/17 end-to-end scenario matches in all three runs and replay,
  compared with 6/8 accepted nodes and 15/17 matches for the unchanged `qwen3:8b` baseline.
- Verified identical source hashes, request objects, prompt/validator versions and configuration
  between models; the measured repository revisions differ only in documentation.
- Confirmed the split node keeps its import at module level and matches the reviewed output arrays.
  The metric node still omits the final standalone `mae` expression and is rejected before execution.
- Compared every live candidate with baseline run 1 and compared candidate run 1 with later runs
  and replay. Cross-model comparisons each found one improved proposal and scenario, with no
  proposal or evaluated-scenario regressions. All eight candidate raw responses were byte-identical.
- Documented the protocol, artifact identities, per-task outcomes and all timings, retaining raw
  artifacts in ignored `generated/` rather than publishing notebook source and model responses.
- Passed all 880 tests on Python `3.12.14` with 100% line and branch coverage, Ruff checks, mypy and
  distribution builds. Production code, prompt, validator, corpus and defaults remain unchanged.

### Decisions

- Treat the code-specialized model as a candidate for the next pilot, not a general accuracy claim.
- Keep strict static rejection and separate it from runtime mismatches; the rejected metric
  proposal's behavioral equivalence remains unmeasured.
- Do not infer a speed advantage from the variable live timings or compare replay model latency.
- Retain the deterministic conversion default and explicit opt-in model selection.

### Open questions

- Can a general statement-retention instruction resolve the remaining rejection for both models?
- How does the candidate perform on fresh task families and complete notebooks?

### Next step

- Introduce a versioned prompt clarification without relaxing validation, using the current corpus
  as development regressions and fresh independent cases for later generalization measurements.

## 2026-10-02 - Expanded qwen3 baseline passes the four new tasks

### Completed

- Captured three live artifacts on dataset `v2` at repository revision
  `4aaf9da417e444aac9dcbe274f274d865e46e357`, using the unchanged `qwen3:8b` model digest,
  Ollama `0.35.0`, Python `3.12.14`, prompt `node-code-v4` and validator `node-code-validation-v4`.
- Reproduced 6/8 statically accepted nodes and 15/17 end-to-end scenario matches in all three runs.
- Verified all twelve scenarios linked to aggregation, joins, categorical encoding and date features,
  including their expected exceptions, with no behavioral mismatch or execution error.
- Confirmed the original two rejection causes: an omitted standalone `mae` expression and a
  duplicated function-local import in the split node. Their two scenarios were not executed.
- Replayed the first artifact offline with the same outcomes and compared it with both later runs
  and the replay; all proposal statuses and evaluated scenario statuses remained unchanged.
- Confirmed byte-identical raw responses for seven tasks and identical function code for all eight;
  the split node varied only by one word in its review note.
- Documented per-task results, provider/execution durations, configuration and artifact identities.
- Passed all 880 tests on Python `3.12.14` with 100% line and branch coverage, plus Ruff lint and
  formatting checks, mypy and distribution builds. No production code or test fixtures changed.

### Decisions

- Preserve the existing prompt, validator and reviewed corpus during this measurement.
- Treat 88.24% on `v2` as a dataset-specific observation, not an improvement over 60% on `v1`:
  the original subset still matches only three of five scenarios.
- Keep raw artifacts private in ignored `generated/`; commit only aggregate, reviewable evidence.
- Distinguish strict static-contract failures from observed behavioral mismatches; rejected proposals
  were not executed and their semantic equivalence remains unmeasured.

### Open questions

- Determine whether another lightweight local code model meets the unchanged fidelity contract.
- Extend evaluation beyond synthetic task cells to representative complete notebooks.

### Next step

- Compare a second local code model on the same eight nodes and seventeen scenarios, retaining the
  same prompt and validator before considering prompt tuning or fine-tuning.

## 2026-10-02 - Independent evaluation expands to eight tasks

### Completed

- Added dataset revision `v2` with eight node references, seventeen behavioral scenarios and
  seventeen invalid code examples, preserving all measured `v1` contracts.
- Added source notebooks for sorted aggregation, validated customer joins, categorical indicators
  and strict date parsing with calendar features.
- Added nominal, boundary and exception scenarios for each new task, including refunds and missing
  amounts, unmatched keys and duplicate customer keys, missing categories, leap days and empty input.
- Verified source hashes, static reference acceptance and rejection of all invalid proposals.
- Executed all seventeen reference scenarios and reviewed proposals successfully, and verified that
  eight semantic negative controls produce behavioral mismatches.
- Verified that the benchmark requests each of the eight nodes once and evaluates all seventeen
  linked scenarios with an offline reference provider.

### Decisions

- Publish an expanded dataset directory while keeping the case schemas at `1.0` and freezing `v1`.
- Author references and expected outputs independently from the V1 generator and model responses.
- Keep string and integer output dtypes explicit, including aggregation keys across pandas versions.
- Keep date values within the existing JSON transport by using date-string inputs and calendar
  string/integer outputs.

### Open questions

- Measure how the current local model generalizes to the new tasks.
- Add complete real-world notebooks and further task families beyond the synthetic task cells.

### Next step

- Run the unchanged `qwen3:8b` prompt and validator on dataset `v2`, then compare another local code
  model on exactly the same evidence before tuning the prompt.

## 2026-10-02 - Repeated qwen3 baseline confirms stable failure modes

### Completed

- Captured three independent live `qwen3:8b` artifacts with Ollama `0.35.0` and complete model,
  runtime and repository provenance.
- Replayed the first artifact offline through the current parser, validator and behavioral worker.
- Compared run 1 against runs 2 and 3 and against its replay.
- Reproduced 2/4 statically accepted nodes and 3/5 end-to-end scenario matches in every live run and
  in replay, with no proposal or scenario regression.
- Confirmed byte-identical raw responses for three tasks; the fourth changed only one explanatory
  word while preserving the same rejected function.

### Decisions

- Do not commit raw artifacts because they contain source and model output; keep only aggregate,
  reviewable measurements in project documentation.
- Treat the first-run provider duration as warm-up affected and retain all three durations rather
  than reporting only the fastest run.
- Classify both failures as systematic prompt/model behavior: one omitted standalone expression and
  one duplicated import inside the function.

### Open questions

- Determine whether these failure modes persist on a broader corpus and another lightweight local
  code model.
- Define representative notebook categories and review criteria for the next held-out cases.

### Next step

- Expand the independent corpus before modifying the prompt, then compare the unchanged baseline
  against at least one other local model on the same reviewed evidence.

## 2026-10-02 - Behavioral benchmarks become replayable evidence

### Completed

- Added artifact schema `1.0` around complete behavioral benchmark reports, including raw model
  responses, canonical report hashes, execution configuration and environment provenance.
- Added atomic exclusive JSON publication so benchmark evidence is never partially written or
  silently replaced.
- Added offline replay through the current parser, static validator and behavioral worker without
  contacting Ollama.
- Added artifact comparison for acceptance, per-node and per-scenario changes, end-to-end behavior,
  execution duration and comparable live-provider latency.
- Added `behavioral-benchmark run`, `replay` and `compare` CLI workflows with deterministic tests.

### Decisions

- Keep the existing benchmark report schema unchanged and place reproducibility metadata in a
  separate versioned envelope.
- Preserve every raw response as the replay input; parsed output alone is insufficient to audit a
  future parser or validator change.
- Set replay provider duration to zero and refuse to present it as comparable live-model latency.
- Continue requiring explicit untrusted-code execution consent for both live runs and replay.

### Open questions

- Define the first larger representative notebook corpus and its review process.
- Decide which prompt and local-model variants should be measured repeatedly before setting a V2
  release threshold.

### Next step

- Capture repeated live artifacts for baseline prompt/model variants, compare their failure modes,
  then expand the held-out corpus before tuning prompts against the current five scenarios.

## 2026-09-28 - Real provider outputs receive end-to-end behavioral metrics

### Completed

- Added behavioral code benchmark schema `1.0` over four independent nodes and five scenarios.
- Added complete corpus preflight before provider I/O and one provider call per shared node.
- Added explicit static acceptance, evaluated-match and end-to-end scenario denominators.
- Kept provider, parsing, static-validation, mismatch and execution failures separate.
- Ran local `qwen3:8b` with prompt `node-code-v4`: 2/4 nodes accepted and 3/5 scenarios matched
  end to end, with no mismatch or runtime failure among accepted proposals.

### Decisions

- Use end-to-end scenario match rate as the primary model-development measure so rejected nodes are
  not hidden by a conditional success rate.
- Reuse one accepted proposal for every reviewed scenario linked to that node.
- Keep real Ollama calls outside default CI and require explicit untrusted-code execution consent.
- Treat the initial 60% result as one small development observation, not an accuracy guarantee.

### Open questions

- Determine whether prompt changes can fix omitted standalone expressions and function-local imports
  without regressing parameter fidelity.
- Expand the independent corpus before selecting a default local model or release threshold.

### Next step

- Preserve raw real-model benchmark reports and compare prompt/model variants on identical evidence,
  then expand the held-out corpus with representative notebooks and reviewed behavioral scenarios.

## 2026-09-28 - Validated proposal execution connected to behavioral comparison

### Completed

- Added `execute_behavioral_proposal` on the same bounded subprocess path as approved references.
- Required request-specific static validation before any proposal process can start.
- Added explicit `allow_untrusted_code_execution=True` consent because the worker is not an OS
  sandbox.
- Added proposal-evaluation report schema `1.0`, combining execution, comparison and the exact
  response SHA-256.
- Passed the four reviewed responses through the proposal path across all five behavioral scenarios.

### Decisions

- Reuse one worker protocol for references and proposals to prevent security and behavior drift.
- Materialize inputs inside every fresh worker so reference and proposal runs never share mutable
  runtime values.
- Keep proposal execution outside automatic generation and require explicit caller authorization.
- Do not claim model accuracy from reviewed reference responses routed through the proposal API.

### Open questions

- Choose a container or OS sandbox before positioning proposal execution for untrusted production
  workloads.
- Decide which local Ollama models and prompts should form the first measured behavioral benchmark.

### Next step

- Run real local-provider proposals against the reviewed cases and add aggregate behavioral,
  latency and failure metrics without weakening deterministic fallback behavior.

## 2026-09-28 - Deterministic behavioral comparison reports implemented

### Completed

- Added comparison report schema `1.0` with distinct matched, mismatch and execution-error states.
- Implemented type-sensitive exact comparison, tolerant numeric comparison, structural array
  comparison and policy-driven table comparison.
- Added exact exception-type and stable message-fragment matching with actionable diagnostics.
- Added deterministic corpus aggregation and canonical dictionary and JSON serialization.
- Compared all five approved reference scenarios successfully, including the expected exception.

### Decisions

- Keep shape and value order structural for arrays; make dtype checking explicit.
- Keep table row order structural while allowing explicit column-order, dtype and index policies.
- Treat worker and serialization failures separately from completed behavioral mismatches.
- Interpret the current `5/5` result as harness validation, not generated-code or model accuracy.

### Open questions

- Choose the isolation boundary required before executing model-proposed functions.
- Decide whether non-finite arrays/tables and richer data types require a behavioral schema update.

### Next step

- Define and implement the isolated proposal-execution boundary, using independently materialized
  inputs before comparing generated code with the approved reference expectations.

## 2026-09-28 - Approved behavioral references execute in isolated workers

### Completed

- Added execution result schema `1.0` for typed outputs, raised exceptions, bounded captures,
  duration and explicit setup, timeout, process and serialization failures.
- Added a fresh-interpreter worker for approved reference functions with `-I`, static revalidation,
  temporary working directories, filtered environments and bounded request/result transport.
- Added configurable deadlines, new process groups and process-tree termination on timeout.
- Executed all five reviewed behavioral scenarios across the independent node-code corpus,
  including the expected missing-column exception.

### Decisions

- Execute only source-controlled, human-approved references in this milestone; model proposals
  remain non-executable until their isolation policy is explicit.
- Treat process separation as fault containment, not an OS sandbox: filesystem and network access,
  plus portable CPU and memory limits, remain unresolved.
- Reuse the tagged behavioral values for subprocess transport and continue to reject pickle,
  arbitrary objects and non-finite runtime outputs.

### Open questions

- Choose the isolation boundary required before executing model-proposed functions.
- Decide whether non-finite arrays/tables and richer data types require a behavioral schema update.

### Next step

- Implement deterministic exact, numeric, array and table comparators for approved reference
  results before enabling execution of any model proposal.

## 2026-09-27 - Behavioral comparison evidence contract defined

### Completed

- Added schema `1.0` for reviewed runtime inputs, outputs, expected exceptions and comparator rules.
- Added immutable tagged values for finite scalars, nested lists/objects, typed arrays and tables.
- Added exact, numeric, array and table comparison specifications with explicit tolerance, dtype,
  ordering and index policies.
- Added five scenarios linked to the independent node-code corpus: four successful workflows and
  one expected missing-column exception.
- Added strict deterministic serialization, duplicate-key and non-finite-value rejection, corpus
  loading, and interface validation against node arguments and outputs.

### Decisions

- Do not use pickle or accept arbitrary Python objects as behavioral evidence.
- Keep comparison intent separate from execution; this milestone imports and runs no proposed code.
- Require array and table outputs to select dedicated comparators so shape, dtype and ordering
  policies stay explicit during review.
- Permit multiple behavioral scenarios for one node-code case, including expected exceptions.

### Open questions

- Define process isolation and resource controls that work consistently on supported platforms.
- Decide how future schemas represent fitted models, sparse data, timestamps and extension dtypes.

### Next step

- Implement a subprocess worker for reviewed reference functions with timeout, temporary-directory,
  environment and output-size controls before comparing any model proposal.

## 2026-09-27 - Independent node-code evaluation corpus established

### Completed

- Added a strict versioned schema and deterministic loader for reviewed node-code cases.
- Added four held-out task notebooks covering custom feature engineering, regression evaluation,
  mixed-type imputation and a two-parameter holdout split.
- Authored four reference functions independently of the planner and V1 generator, plus nine
  reviewed invalid proposals covering omissions, changed operations, malformed syntax, missing or
  local imports, ignored parameters, nested mappings and swapped arguments.
- Added SHA-256 and exact-code-cell provenance checks for every case.
- Added separate compilation, static validation, reference AST, expected-diagnostic, detected-error
  and false-rejection metrics. All four references pass and all nine invalid examples are detected.

### Decisions

- Keep this corpus provider-free: it evaluates stored reviewed responses and makes no Ollama call.
- Require explicit approval and at least one invalid example per case.
- Keep source provenance independent from planning and generation so implementation output cannot
  silently become its own ground truth.
- Treat the initial corpus as a validator regression baseline, not representative model accuracy.

### Open questions

- Select rights-cleared real-world notebooks to expand beyond small synthetic tasks.
- Define serializable runtime inputs and output comparators for isolated behavioral evaluation.

### Next step

- Specify and implement an isolated behavioral-comparison contract before executing any proposed
  node code or integrating it into generated projects.

## 2026-09-27 - Source fidelity checked for all proposed node bodies

### Completed

- Extended the existing source-derived AST check to parameter-free tasks in validator v4.
- Added regressions for deleted, added, reordered and modified instructions, including standalone
  expressions, nested operations, docstrings and assignments preceding unchanged assertions.
- Kept formatting and comments flexible and verified that validation does not execute accepted
  source effects or rejected proposal effects.
- Replayed the same 104 stored model responses without calling Ollama. Six proposals are newly
  rejected for omitting `accuracy`; no previously matching function is rejected. The default
  prompt now has 19 accepted and V1-matching functions out of 26. All 26 V1 references still pass.

### Decisions

- Reuse one full-body comparison rather than adding a second rule set for parameter-free tasks.
- Preserve parameter-substitution evidence and the stricter assertion-block guard unchanged.
- Keep prompts, JSON schemas and deterministic project generation unchanged. Model proposals
  remain non-executed review artifacts, not an alternative project-writing path.
- Treat the convergence of acceptance and AST-match counts as a consequence of the strict
  validator, not proof of runtime correctness or improved model accuracy.

### Open questions

- Strict AST fidelity also rejects equivalent rewrites and cannot justify arbitrary refactorings.
- Independent references and held-out notebooks are needed beyond this small synthetic corpus.

### Next step

- Build independent reviewed evaluation examples and specify isolated behavioral checks before
  widening the accepted transformations or integrating model proposals into project generation.

## 2026-09-27 - Exact parameter substitutions enforced in node proposals

### Completed

- Added validator v3: parameterized function bodies must match original source after the exact
  V1-derived substitutions, excluding the already validated terminal return.
- Added adversarial checks for nested lists, ignored and swapped arguments, argument overwrites,
  non-target changes, missing or ambiguous evidence, and non-execution of untrusted expressions.
- Replayed 104 recorded responses from prompt experiments v1 through v4 with unchanged requests,
  notebook hashes and reference functions, without contacting Ollama.
- Detected six formerly accepted invalid proposals: three ignored parameters in v2 responses and
  three nested-list substitutions in v3 responses. Default v1 stays at 21 accepted / 19 matching
  functions out of 26; v4 stays at 20 / 18. All 26 V1 reference functions still pass.

### Decisions

- Require whole-body AST preservation for parameterized tasks rather than allowing arbitrary
  rewrites around a correctly placed argument. Potentially equivalent refactorings also fail.
- Keep parameter-free tasks and the conservative assertion-block guard unchanged. The validator
  does not patch, execute, or write proposals into projects.
- Retain prompt v1 by default, optional evidence prompt v4, request/response schema `1.0` and
  benchmark schema `1.1`; record the changed validator identity in every new report.
- Store raw replay reports locally under ignored `generated/`, not in the public repository.

### Open questions

- Broader parameter patterns and substitutions inside assertion-containing blocks need explicit
  transformation rules before widening acceptance.
- Static acceptance does not establish runtime configuration validity or behavioral equivalence.

### Next step

- Address remaining source-statement and import-placement deviations using reviewed examples,
  then broaden independent evaluation and design isolated behavioral comparisons.

## 2026-09-22 - Comparative planner benchmark runner implemented

### Completed

- Added a reusable runner that analyzes each corpus notebook once and evaluates named planners over
  the same static facts.
- Added per-case planning latency, deterministic validation status, semantic fallback detection,
  and the existing structure-quality metrics.
- Added aggregate exact-match, valid-plan, fallback, total-latency, and mean-latency statistics.
- Added planning benchmark schema `1.0` with source paths and SHA-256 identities.
- Added a CLI `benchmark` command that compares deterministic and local hybrid planners and emits
  JSON to stdout.

### Decisions

- Timing covers planner execution only so notebook loading and static analysis do not distort model
  comparisons.
- Hybrid CLI runs include the local model name in the planner label.
- Provider failures remain measured fallbacks rather than aborted benchmark runs.
- Live Ollama execution stays opt-in and outside the default CI suite.
- Generated-code behavior, reviewer corrections, tokens, energy, and cost require separate future
  evaluation contracts.

### Open questions

- Select the first local models and hardware tiers for controlled measurements.
- Decide which aggregate thresholds should gate a V2 preview.
- Add broader, rights-cleared notebooks before treating results as representative.

### Next step

- Install Ollama locally, select an initial lightweight model, run the benchmark, and record the
  first measured baseline without committing model weights or private notebook content.

## 2026-09-22 - Explicit planner selection exposed

### Completed

- Added public deterministic and hybrid planner modes plus a planner construction helper.
- Added explicit planner selection and local Ollama model, URL, and timeout settings to the Python
  path-planning API.
- Added the same options to the CLI `plan` and `generate` commands.
- Added concise configuration errors for missing models, invalid local-provider settings, and
  incompatible custom-planner options.
- Documented deterministic defaults, hybrid opt-in, and fallback behavior.

### Decisions

- Deterministic planning remains the zero-configuration default in every public entrypoint.
- Hybrid mode requires an explicit downloaded Ollama model name; the project does not silently
  select or download a model.
- Custom planner injection remains supported and cannot be mixed with built-in Ollama settings.
- Provider availability is a planning outcome, not a CLI configuration error, so it continues to
  produce a reportable deterministic fallback.

### Open questions

- Select candidate local models after benchmarking them on the versioned corpus.
- Decide whether generation should write the conversion report beside the generated project.

### Next step

- Run controlled local-model benchmarks on the planning corpus and record semantic quality,
  fallback rate, latency, memory requirements, and recommended hardware tiers.

## 2026-09-22 - Safe hybrid plan assembly implemented

### Completed

- Added `HybridSemanticPlanner` as a provider-backed implementation of the planner protocol.
- Added deterministic assembly for semantic task renaming and adjacent task grouping.
- Recomputed task interfaces, source, diagnostics, and renamed parameters from V1 evidence rather
  than trusting model-provided executable details.
- Added provider, model, prompt, review-note, interface-adjustment, and fallback diagnostics to
  conversion reports.
- Added deterministic fallback for provider and assembly failures and bypassed providers for
  statically blocked notebooks.
- Verified renamed parameterized nodes through generated Kedro source.

### Decisions

- Semantic suggestions may change structure but cannot replace static facts.
- The first assembler groups only complete, adjacent deterministic tasks to preserve execution
  order and source provenance.
- Suggested interfaces are evaluation signals; final executable interfaces are derived from V1.
- Non-default pipeline IDs remain unsupported until generation and registry wiring support
  multiple pipelines end to end.

### Open questions

- Define an open semantic intent field without introducing a closed task taxonomy.
- Define safe statement-level splitting for transformations that contain several independent
  operations in one notebook cell.
- Add multi-pipeline generation before accepting arbitrary semantic pipeline assignments.

### Next step

- Add explicit deterministic or hybrid planner selection to the Python API and CLI while keeping
  deterministic planning as the default.

## 2026-09-22 - Local Ollama semantic provider implemented

### Completed

- Added an Ollama provider for non-streaming structured chat completions through the standard
  library HTTP client.
- Passed the semantic response JSON Schema to Ollama and selected deterministic temperature-zero
  generation.
- Added configurable request timeout and maximum response size.
- Normalized timeout, connection, HTTP, generation, malformed-envelope, and oversized-response
  failures into stable provider errors.
- Added offline tests for the exact HTTP request, orchestration integration, failure handling, and
  local URL restrictions.

### Decisions

- The adapter accepts only loopback HTTP URLs and rejects known Ollama cloud-model tags.
- Strict local isolation must also be enforced in Ollama with cloud features disabled because a
  local server can proxy cloud inference.
- Remote transmission requires a separate consent and credential design.
- Ollama and model installation remain optional and are excluded from default CI.
- Structured provider output still cannot reach Kedro generation before hybrid plan assembly and
  deterministic validation.

### Open questions

- Select candidate local models only after measuring them on the reviewed planning corpus.
- Define whether retries belong in the provider adapter or a provider-neutral policy wrapper.
- Define the accepted-suggestion merge algorithm and deterministic task-ID assignment.

### Next step

- Assemble accepted semantic suggestions into a `ConversionPlan` while preserving static facts,
  deterministic IDs, diagnostics, and fallback behavior.

## 2026-09-22 - Deterministic fake semantic provider implemented

### Completed

- Added a provider-neutral raw completion protocol and provider request contract.
- Added deterministic `planning-v1` prompt rendering with explicit static-evidence rules.
- Added a configurable fake provider that records calls and returns fixed JSON or fixed expected
  failures without I/O.
- Added orchestration for parsing, static cross-validation, invocation traces, and explicit V1
  fallback.
- Tested valid output, provider timeout, malformed JSON, semantically invalid output, unsupported
  prompt versions, and unexpected provider errors.

### Decisions

- Providers own transport only; they do not validate or merge their output.
- Only expected `SemanticProviderError` and response-contract failures trigger fallback.
- Configuration errors and programming errors are not hidden behind fallback.
- A valid semantic response remains a suggestion until a separate hybrid assembly step produces
  and validates a final `ConversionPlan`.

### Open questions

- Define HTTP timeout, retry, cancellation, and local endpoint configuration for the first real
  adapter.
- Decide whether the initial local adapter should target Ollama only or a small generic HTTP
  interface shared by compatible runtimes.

### Next step

- Implement an optional local Ollama adapter through the standard library HTTP client, without a
  provider SDK dependency.

## 2026-09-22 - Structured semantic suggestion contracts implemented

### Completed

- Added versioned, immutable request, response, task suggestion, invocation trace, and result
  contracts for semantic planning.
- Added deterministic request and response serialization plus a strict structured-output JSON
  schema.
- Added cross-validation against V1 facts and the deterministic baseline plan.
- Added valid and invalid contract fixtures and documented the provider trust boundary.

### Decisions

- Static facts and the deterministic plan remain authoritative; a model can suggest grouping,
  naming, interfaces, parameters, and pipeline assignment but cannot invent or drop source facts.
- Provider and model metadata are attached by the orchestrator rather than trusted from model
  output.
- Planning response validation and generated-code review remain separate gates.
- Contract fixtures test compatibility; the reviewed planning corpus measures planner quality.

### Open questions

- Define how accepted suggestions are converted into deterministic task IDs and a final
  `ConversionPlan`.
- Decide which prompt context can be reduced for small local models without losing provenance.

### Next step

- Implement a deterministic fake provider and orchestration path for prompt, parsing, trace,
  failure, and fallback tests.

## 2026-09-22 - Versioned planning evaluation corpus implemented

### Completed

- Added immutable contracts and deterministic JSON serialization for reviewed planning cases.
- Added four approved V1 cases covering 26 task structures across the existing notebook fixtures.
- Preserved source hashes, cell and statement provenance, raw code, node names, inputs, outputs,
  parameters, diagnostics, and expected pipeline assignments.
- Added dimension-level planning metrics and exact-match evaluation.
- Established the deterministic planner as an exact-match baseline on all four reviewed cases.

### Decisions

- Planning and generated-code evaluation use separate datasets so their failures remain
  attributable.
- Proposed tasks are matched to reviewed tasks by source boundaries, not by predicted names.
- Controlled fixtures seed the evaluation system but do not constitute a representative accuracy
  benchmark for real-world notebooks.
- Only explicitly approved examples can enter the gold corpus.

### Open questions

- Define provenance, licensing, and redaction metadata for real-world notebook cases.
- Decide the minimum corpus size and diversity required before fine-tuning a planner.
- Define separate code-generation and reviewer datasets after the semantic response contract.

### Next step

- Define versioned request and response contracts for structured semantic planner suggestions.

## 2026-09-22 - Provider-neutral semantic planner boundary implemented

### Completed

- Added the `SemanticPlanner` protocol for conversion planning from `NotebookFacts`.
- Wrapped the V1 rules in `DeterministicSemanticPlanner` without changing their behavior.
- Allowed callers to inject a planner into `plan_notebook_path`.
- Kept deterministic planning as the default for the Python API and CLI.
- Added tests for protocol conformance and planner injection.

### Decisions

- Planner implementations consume deterministic facts and return the existing validated
  `ConversionPlan` contract.
- Provider selection remains an orchestration concern and does not enter the analyzer or Kedro
  generator.
- The initial CLI remains deterministic until provider configuration and failure behavior are
  explicitly defined.

### Open questions

- Define the versioned request and response contracts used by an LLM-assisted planner.
- Decide how planner identity and model metadata should be recorded in conversion reports.

### Next step

- Build a versioned planning evaluation corpus from the reviewed V1 fixtures.

## 2026-09-22 - Deterministic MVP release prepared

### Completed

- Documented the `0.1.0` deterministic MVP capabilities and known limitations.
- Added release installation and quick-start instructions.
- Defined a reproducible annotated-tag and GitHub Release process.
- Added a tag-triggered workflow that validates the version, runs deterministic checks, builds
  distributions, and creates a draft GitHub Release.

### Decisions

- The deterministic V1 milestone is released as `0.1.0`, not `1.0.0`, while the public API and
  supported notebook subset continue to evolve.
- Git tags are immutable release snapshots; feature development continues from `main`.
- GitHub releases remain pre-releases during the `0.x` series.
- PyPI publication is deferred until package naming and publication policy are finalized.

### Open questions

- Decide when the package is ready for trusted publishing to PyPI.
- Decide which compatibility guarantees begin with the first stable `1.0.0` release.

### Next step

- Tag the merged release commit as `v0.1.0`, publish the generated draft release, then begin the
  provider-neutral semantic planner protocol for V2.

## 2026-09-22 - V2 hybrid planning roadmap defined

### Completed

- Documented the conversion contract from notebook facts to explicit workflow steps and faithful Kedro nodes.
- Replaced the hypothetical LLM section with a concrete hybrid-planning architecture.
- Split the roadmap into the completed deterministic V1 foundation and four measurable V2 phases.
- Updated the project status to reflect the working planner, report, validator, and Kedro generator.

### Decisions

- Static analysis remains authoritative and the deterministic mode remains the default.
- LLM assistance is optional, provider-neutral, validated, traceable, and visible during review.
- The LLM may propose semantic structure and node code but cannot write directly to the generated project.
- Behavioral equivalence, not merely successful execution, remains the conversion target.

### Open questions

- Choose the first optional provider adapter after the provider-neutral contract is implemented.
- Define the initial benchmark corpus and acceptable V2 preview thresholds.
- Specify the redaction and consent policy for remote providers.

### Next step

- Introduce the provider-neutral `SemanticPlanner` protocol while preserving the current deterministic planner as the default implementation.

## 2026-09-21 - Structured parameters made readable in reports

### Completed

- Rendered structured sequence parameters as readable list literals in Markdown reports.
- Rendered structured mapping parameters as readable dictionary literals in Markdown reports.
- Added unit coverage for pandas `drop(columns=...)` and `fillna({...})` parameter shapes.

### Decisions

- Report values use the same deterministic representation as generated Kedro configuration.
- The immutable tuple representation remains an internal planning detail and is not exposed to reviewers.

### Open questions

- Decide whether dataframe schema hints should validate extracted column names.
- Select the next pandas operations to support, starting with `rename` or `replace`.

### Next step

- Add schema-aware diagnostics for selected pandas operations or support another common pandas transformation pattern.

## 2026-09-11 - Pandas preprocessing parameter extraction implemented

### Completed

- Extracted selected literal pandas preprocessing arguments into `ConversionPlan` parameters.
- Supported `fillna(value=...)`, positional `fillna({...})`, and `drop(columns=[...])`.
- Rewrote generated Kedro node code to consume those pandas arguments through `params:` inputs.
- Extended generated `parameters.yml` rendering to preserve simple lists and string-keyed mappings.
- Added planner, integration, generation, and end-to-end coverage for pandas parameterized preprocessing.

### Decisions

- Structured parameter values remain immutable in the planning IR and are rendered back to YAML lists or mappings during generation.
- Sklearn parameter extraction remains limited to scalar JSON-compatible literals.
- `assign` expressions are not parameterized yet because they often depend on dataframe columns or arbitrary expressions.

### Open questions

- Decide whether dataframe schema hints should validate extracted `drop(columns=...)` values.
- Decide how to parameterize simple `assign` constants without obscuring column-expression logic.
- Add support for more dataframe operations such as `rename`, `replace`, and joins.

### Next step

- Improve review/report rendering for structured parameter values, or add dataframe schema diagnostics around selected pandas operations.

## 2026-09-11 - Pandas preprocessing naming patterns implemented

### Completed

- Added deterministic task naming for simple pandas dataframe rewrites:
  `dropna` as `clean_data`, `fillna` as `impute_missing_values`, and `assign` as `engineer_features`.
- Kept existing mixed feature-preparation cells named from Markdown headings instead of over-classifying them as cleaning tasks.
- Added a pandas preprocessing reference notebook with missing-value imputation and feature engineering.
- Added integration coverage for pandas preprocessing task names and dataframe redefinition flow.
- Added end-to-end equivalence coverage comparing the pandas preprocessing notebook accuracy with the generated Kedro pipeline.
- Reached 100% statement and branch coverage with 171 passing tests.

### Decisions

- The first pandas support improves semantic naming only; generated code still preserves the source pandas expressions.
- Patterns trigger on direct dataframe rewrites to keep the heuristic conservative.
- Argument parameterization for pandas transformations remains separate from naming.

### Open questions

- Decide which pandas arguments should become Kedro parameters.
- Add support for joins, groupby aggregations, and column normalization patterns.
- Decide whether dataframe schema hints belong in `ConversionPlan`.

### Next step

- Add pandas parameter extraction for simple literal `fillna` and selected `drop`/`assign` arguments, or add richer data-source catalog support.

## 2026-09-11 - StandardScaler preprocessing pattern implemented

### Completed

- Added a scaled reference notebook fixture using `StandardScaler`.
- Recognized scaling cells using `fit_transform` and `transform` as `scale_features` tasks.
- Extracted literal `StandardScaler(with_mean=..., with_std=...)` parameters into Kedro configuration.
- Rewrote generated scaler construction to consume Kedro `params:` inputs.
- Added integration coverage for the planned scaling task and its parameters.
- Added generated-project tests for scaler imports, node signatures, parameterized source, and pipeline parameter wiring.
- Added end-to-end equivalence coverage comparing the scaled notebook accuracy with the generated Kedro pipeline.
- Reached 100% statement and branch coverage with 168 passing tests.

### Decisions

- The first sklearn preprocessing support is intentionally limited to explicit `StandardScaler` usage in sequential code.
- Scaling task naming is triggered only when transform calls produce `_scaled` outputs.
- Broader sklearn pipeline and `ColumnTransformer` support remains out of scope until represented by dedicated fixtures.

### Open questions

- Add support for `fit_transform` outputs that do not use `_scaled` suffixes.
- Decide how to model reusable transformer objects in the catalog or as intermediate memory datasets.
- Add `ColumnTransformer` and sklearn `Pipeline` support after simple transformer patterns are stable.

### Next step

- Add more pandas transformation patterns such as `assign`, `fillna`, and `merge`, because they are common before sklearn preprocessing.

## 2026-09-11 - Reviewable plan diagnostics implemented

### Completed

- Added `PlanDiagnostic` records to `ConversionPlan`.
- Emitted deterministic plan diagnostics for fallback task names, inherited source diagnostics, unresolved external inputs, and tasks without data outputs.
- Added blocking plan diagnostics for source-level blockers that prevent task planning.
- Rendered plan diagnostics in the Markdown conversion report.
- Updated planner and reporting tests for the new review signals.
- Reached 100% statement and branch coverage with 164 passing tests.

### Decisions

- Plan diagnostics are review notes, not validation failures by default.
- Diagnostics use stable `PDxxx` codes so future CLI or UI surfaces can filter them.
- The current diagnostic payload is intentionally small: code, severity, message, and optional task ID.

### Open questions

- Decide whether plan diagnostics should carry source cell IDs directly.
- Decide whether warnings should be suppressible once reviewed.
- Add richer diagnostic messages using source diagnostic details rather than only inherited codes.

### Next step

- Expand pandas and scikit-learn semantic patterns now that the review and validation surfaces can expose uncertainty.

## 2026-09-11 - Conversion plan validation implemented

### Completed

- Added `validate_conversion_plan(plan)` as a public API.
- Added `ConversionPlanValidationError` for plans that are unsafe to generate.
- Validated blocking diagnostics, duplicate task IDs, duplicate task names, duplicate catalog dataset names, duplicate parameter names, duplicate parameter function arguments, invalid task identifiers, and unknown task parameter references.
- Wired CLI `generate` to validate plans before writing files.
- Extended friendly CLI error handling to plan validation failures.
- Added unit tests for valid plans, each validation category, package exports, and blocked CLI generation.
- Reached 100% statement and branch coverage with 163 passing tests.

### Decisions

- Plan validation lives in the semantic boundary because it checks conversion-plan intent before generator-specific rendering.
- The Kedro generator keeps its local safety checks, but CLI generation now performs explicit validation first.
- The first validation API raises a concise exception instead of returning a richer report object.

### Open questions

- Decide whether validation should return structured findings for machine-readable CLI and CI output.
- Add diagnostic messages to blocked-plan validation once `ConversionPlan` preserves more diagnostic detail.
- Decide whether generated projects should embed a copy of the validation report.

### Next step

- Add richer plan diagnostics for ambiguous or unsupported notebook patterns so validation/reporting can explain conversion risk beyond hard syntax blockers.

## 2026-09-11 - Friendly CLI errors implemented

### Completed

- Caught expected notebook loading and project generation errors at the CLI boundary.
- Printed concise `Error: ...` messages to stderr instead of exposing stack traces.
- Returned a stable non-zero exit code for expected CLI failures.
- Preserved raw propagation for unexpected programming errors.
- Added CLI tests for missing notebook files and existing output directories.
- Reached 100% statement and branch coverage with 155 passing tests.

### Decisions

- Error formatting belongs in `cli.py`, not in lower-level loading, planning, or generation modules.
- The first stable failure exit code is `1` for expected operational errors.
- `argparse` remains responsible for command syntax errors.

### Open questions

- Decide whether distinct expected error categories should receive distinct exit codes.
- Decide whether CLI errors should support a machine-readable JSON mode.
- Add friendlier context for plans blocked by diagnostics.

### Next step

- Add explicit plan validation/reporting for blocked diagnostics before generation so users can see why a notebook cannot be converted.

## 2026-09-11 - Kedro generation CLI implemented

### Completed

- Added `notebook-to-kedro generate NOTEBOOK OUTPUT_DIR`.
- Wired generation through the existing public planning and Kedro generation APIs.
- Added optional `--project-root` and `--package-name` support.
- Printed the generated project destination and created file list to stdout.
- Covered successful generation, project-root normalization, and existing-destination rejection.
- Reached 100% statement and branch coverage with 154 passing tests.

### Decisions

- The CLI now supports the full manual flow: run `plan`, review the report, then run `generate`.
- Generation errors still propagate from the underlying API for now, keeping this feature focused.
- Output lists created paths directly so shell users can inspect or redirect it without extra parsing rules.

### Open questions

- Decide CLI error formatting for user-facing failures.
- Decide whether `generate` should optionally print or save the report before writing files.
- Add an `--output` option for reports if redirecting stdout is not enough.

### Next step

- Add friendly CLI error handling for notebook load errors and project generation errors.

## 2026-09-11 - Minimal planning CLI implemented

### Completed

- Added a `notebook-to-kedro` console script.
- Implemented `notebook-to-kedro plan NOTEBOOK`.
- Wired the command through the public planning and reporting APIs.
- Added optional `--project-root` support for portable notebook paths in reports.
- Added CLI unit tests for successful report output, project-root normalization, and missing commands.
- Reached 100% statement and branch coverage with 151 passing tests.

### Decisions

- The initial CLI only exposes planning/reporting, because generation still benefits from explicit review.
- CLI parsing stays thin and delegates analysis, planning, and reporting to existing public APIs.
- The command writes Markdown to stdout so it can be redirected to a file or viewed directly.

### Open questions

- Decide CLI error formatting for notebook load and generation failures.
- Add a `generate` command once report review and plan validation are sufficiently explicit.
- Decide whether report output should support `--output`.

### Next step

- Add a CLI `generate` command that creates a Kedro project from a notebook path after the static planning path is available from the terminal.

## 2026-09-11 - Conversion report renderer implemented

### Completed

- Added `render_conversion_report(plan)` as a public API.
- Rendered deterministic Markdown summaries for conversion plans.
- Included proposed task candidates with source cells, inputs, outputs, parameters, and diagnostics.
- Included catalog datasets, extracted parameters, and blocking diagnostic codes.
- Added Markdown escaping for table-sensitive values.
- Covered complete, empty, blocked, and escaping cases in unit tests.
- Reached 100% statement and branch coverage with 148 passing tests.

### Decisions

- The first report format is Markdown because it is readable in terminals, PRs, and docs.
- Reporting depends only on `ConversionPlan`; it does not import Kedro or re-read notebooks.
- Empty sections are explicit instead of omitted so reviewers can distinguish "none found" from missing output.

### Open questions

- Decide whether future reports should include diagnostic messages, not only codes.
- Decide whether to add JSON report output for machines and CI annotations.
- Decide how the future CLI should write or print reports.

### Next step

- Add a minimal CLI for planning/reporting so a user can run the static review flow from a notebook path.

## 2026-09-11 - Readable deterministic node names implemented

### Completed

- Added deterministic task naming before parameter extraction.
- Derived task names from recognized source patterns such as split, train, predict, evaluate, and load.
- Used the nearest preceding Markdown heading as a fallback naming signal.
- Kept generated names as valid Python identifiers and made duplicates deterministic with numeric suffixes.
- Renamed extracted parameter keys to follow the readable node names, such as `split_data.test_size`.
- Updated unit, integration, generation, and end-to-end expectations.
- Reached 100% statement and branch coverage with 143 passing tests.

### Decisions

- Source patterns take precedence over Markdown headings because they are tied to executable evidence.
- Markdown headings are still useful review signals for transformation cells without recognized library calls.
- `cell_0000` remains the final fallback when no reliable semantic cue exists.

### Open questions

- Decide whether to expose naming confidence or provenance in `ConversionPlan`.
- Add richer transformation naming beyond the current ML workflow patterns.
- Decide when a naming proposal should require human review instead of being accepted automatically.

### Next step

- Add conversion report output so users can review planned nodes, parameters, catalog inputs, and diagnostics before trusting the generated project.

## 2026-09-11 — Selected Kedro parameter extraction implemented

### Completed

- Added `ParameterValue` records to `ConversionPlan`.
- Extracted literal parameters from supported scikit-learn calls:
  `train_test_split(test_size=..., random_state=...)` and
  `RandomForestClassifier(n_estimators=..., random_state=...)`.
- Attached extracted parameter names to their task candidates.
- Generated `conf/base/parameters.yml` for extracted values.
- Rewrote generated node code to use function arguments instead of hardcoded keyword literals.
- Wired generated Kedro nodes with `params:<name>` inputs.
- Updated end-to-end tests to load generated parameters into the in-memory Kedro catalog.
- Reached 100% statement and branch coverage with 141 passing tests.

### Decisions

- The first parameter extraction pass is deterministic and limited to literal JSON-compatible values.
- Parameter keys are cell-scoped, such as `cell_0006.test_size`, until semantic node naming exists.
- Unsupported or non-literal keyword values remain in source code rather than being guessed.

### Open questions

- Decide how reviewed semantic node names should rename parameter keys.
- Decide whether repeated parameter values should be deduplicated across nodes.
- Extend parameter extraction to pandas and user-defined transformation thresholds.

### Next step

- Generate more reviewable node names from notebook headings or simple source patterns.

## 2026-09-11 — File-backed CSV catalog fixture implemented

### Completed

- Added a second reference notebook that loads a local CSV with `pd.read_csv`.
- Added a small deterministic tabular classification CSV fixture.
- Extended `ConversionPlan` with proposed catalog datasets.
- Detected simple `pd.read_csv("...")` assignments as CSV catalog inputs.
- Skipped CSV loading cells when creating task candidates so generated nodes consume catalog inputs.
- Generated `conf/base/catalog.yml` entries with `kedro_datasets.pandas.CSVDataset`.
- Copied detected source CSV files into the generated project's `data/01_raw/` directory.
- Added unit, integration, and end-to-end coverage for the file-backed workflow.
- Verified that the generated Kedro pipeline matches the source notebook final accuracy for the CSV-backed fixture.

### Decisions

- The first catalog pattern requires a literal string filepath in a direct `read_csv` assignment.
- The generated project declares `kedro-datasets[pandas]` when CSV catalog support is used.
- End-to-end tests still execute with in-memory datasets while loading the generated-project copy of the CSV.

### Open questions

- Add support for parameter extraction before broadening catalog formats.

### Next step

- Extract simple literal parameters such as `test_size`, `random_state`, and `n_estimators` into a generated `parameters.yml`.

## 2026-09-10 — Generated pipeline equivalence test implemented

### Completed

- Added an end-to-end test for the reference notebook-to-Kedro path.
- Executed the source notebook with `nbclient` to obtain the expected final accuracy.
- Generated a Kedro project from `plan_notebook_path` and `generate_kedro_project`.
- Imported the generated pipeline package from the temporary project source tree.
- Ran the generated Kedro pipeline with `SequentialRunner` and in-memory datasets.
- Compared the generated pipeline's final `accuracy` output with the executed notebook output.
- Reached 100% statement and branch coverage with 130 passing tests.

### Decisions

- The first equivalence check compares the final accuracy because it is the stable observable output already exposed by the reference notebook.
- The generated pipeline is executed in memory to avoid introducing catalog files before the file-backed dataset fixture exists.
- Intermediate predictions are not compared yet because Kedro may release intermediate in-memory datasets after execution.

### Open questions

- Decide which intermediate artifacts should be persisted or captured for richer equivalence checks.
- Add a file-backed fixture before implementing catalog generation.
- Decide how to separate fast default tests from heavier end-to-end validation as the suite grows.

### Next step

- Add a second fixture with file-backed tabular input and generate a minimal Kedro catalog for it.

## 2026-09-10 — Minimal Kedro project skeleton generator implemented

### Completed

- Added a Kedro generation boundary that consumes `ConversionPlan`.
- Generated a minimal project skeleton with `pyproject.toml`, package files, pipeline registry, nodes, and pipeline definition.
- Rendered task candidates as node functions while preserving source code and notebook imports.
- Remapped repeated symbol outputs to unique Kedro dataset names such as `df__cell_0005`.
- Rejected existing destinations to avoid silent overwrites.
- Rejected generation when blocking diagnostics are present.
- Exposed `generate_kedro_project` through the package-level API.
- Added tests that import the generated Kedro pipeline and verify the reference fixture produces six nodes.

### Decisions

- The first generator targets an importable skeleton before running a full Kedro project.
- Generated project dependencies include Kedro, pandas, and scikit-learn for the controlled reference fixture.
- Dataset names are derived from source symbols, with version suffixes only when a symbol is redefined.
- Catalog generation, parameter extraction, and project execution are deferred to later increments.

### Open questions

- Decide how generated projects should declare catalog entries for file-backed datasets.
- Decide how task candidates should be reviewed or renamed before rendering production node names.
- Decide whether mutable estimator flows should remain single-cell nodes or become explicit train/predict abstractions.

### Next step

- Add an end-to-end fixture that executes the generated Kedro pipeline and compares observable outputs with the source notebook.

## 2026-09-10 — Minimal task planner implemented

### Completed

- Added immutable `ConversionPlan` and `TaskCandidate` contracts for proposed Kedro-oriented tasks.
- Added a deterministic `plan_tasks` planner that creates one task candidate per analyzable code cell with data outputs.
- Skipped markdown, raw, empty, and import-only cells.
- Derived task inputs from resolved dependencies plus unresolved non-import reads that still require review.
- Exposed `plan_notebook_path` as a package-level API that loads, analyzes, and plans a notebook path.
- Added unit and integration coverage for planning the reference notebook.

### Decisions

- The first planner is deterministic and does not use an LLM.
- Planning stops when blocking diagnostics are present in the source facts.
- Task names are stable cell-derived identifiers until semantic naming is introduced.
- The planner proposes task boundaries only; Kedro files are not generated in this increment.

### Open questions

- Decide how task candidates should be reviewed and renamed before generation.
- Decide how imports should be represented in the future generated module.
- Decide whether adjacent code cells should be merged before Kedro node generation.

### Next step

- Implement minimal Kedro project generation from reviewed task candidates for the controlled reference fixture.

## 2026-09-10 — Public analysis API implemented

### Completed

- Added `analyze_notebook_path` as the package-level entrypoint for loading and analyzing a notebook path.
- Reused the existing validated notebook loader and deterministic analyzer instead of adding a separate analysis path.
- Added unit coverage for the root package export.
- Added integration coverage for analyzing the reference notebook through the public API.

### Decisions

- The public API accepts file paths while the lower-level analyzer continues to accept an already loaded notebook model.
- The API returns `NotebookFacts` directly so downstream planning and reporting can build on the same canonical IR.
- CLI commands and human-readable reports remain out of scope for this increment.

### Open questions

- Decide whether the first user-facing report should be JSON-only, Markdown, or a typed report model.
- Decide how loader exceptions should be surfaced once a CLI or conversion report exists.

### Next step

- Implement a minimal task planner that groups analyzable code cells into Kedro-oriented task candidates without generating project files yet.

## 2026-09-10 — Cross-cell dependency resolution implemented

### Completed

- Added a dependency resolver that links a statement read to the most recent earlier data definition in physical cell order.
- Integrated dependency resolution into the deterministic analyzer output.
- Kept same-cell reads represented as statement facts without producing cross-cell dependency edges.
- Ignored imported names as dependency producers while still satisfying reads of imported bindings.
- Added `DF001` diagnostics for reads without a known producer or import binding.
- Added `DF002` diagnostics for repeated top-level data definitions.
- Updated the reference notebook analysis integration test to assert reviewed dependency symbols.
- Reached 100% statement and branch coverage with 116 passing tests.

### Decisions

- Dependency facts are cross-cell edges only because the current IR requires producer cells to precede consumer cells.
- The resolver uses physical source order and does not inspect execution counters or runtime object identity.
- Imported names remain symbol facts of kind `import` but do not produce dependency facts.
- Same-statement writes do not satisfy reads from that same statement.

### Open questions

- Decide whether same-cell producer/consumer relationships need their own fact type in a future schema version.
- Decide when execution counter inconsistency should emit `NB003`.
- Refine unresolved-read handling once local scope and function-body free-variable analysis are implemented.

### Next step

- Implement an analysis report or public `analyze` API that loads a notebook path and returns `NotebookFacts`.

## 2026-09-10 — Cell-level AST analysis implemented

### Completed

- Added a deterministic AST analyzer that consumes `LoadedNotebook` and returns `NotebookFacts`.
- Preserved non-code cells while extracting code-cell statements, imports, calls, reads, and writes.
- Recorded regular imports, from-imports, function definitions, class definitions, assignments, tuple/list unpacking writes, attribute reads, subscript reads, ordinary calls, and method calls.
- Added blocking diagnostics for invalid Python syntax, Jupyter magics, shell escapes, and dynamic execution calls.
- Added mutation warnings for known estimator-style mutating method calls such as `fit`.
- Categorized discovered symbols as imports, data, functions, classes, or unknown reads.
- Added unit tests for AST extraction and an integration test for the reference Iris notebook analysis.
- Reached 100% statement and branch coverage with 112 passing tests.

### Decisions

- The analyzer returns `NotebookFacts` with empty dependency facts until cross-cell dependency resolution is implemented.
- Cell-level reads include unresolved names as `unknown` symbols rather than emitting unresolved-dependency diagnostics in this increment.
- Calls are represented syntactically; referenced notebook packages are never imported by the analyzer.
- The initial mutation heuristic is deliberately narrow and currently covers selected estimator-style methods.

### Open questions

- Decide how broad the first mutation and side-effect heuristic should be beyond estimator-style method calls.
- Decide whether unresolved local reads should emit `DF001` during symbol construction or only after dependency resolution.
- Define how function body free variables should be reported once scope analysis is introduced.

### Next step

- Implement cross-cell symbol and dependency resolution from the collected cell-level reads and writes.

## 2026-09-10 — Notebook loader implemented

### Completed

- Added a notebook loading boundary with immutable source models for loaded notebooks and cells.
- Loaded notebooks through `nbformat` without converting their declared notebook format version.
- Validated that notebooks use `nbformat` major version 4 and are identified as Python through language metadata or kernelspec metadata.
- Preserved physical cell order, cell source, execution counters, kernel name, relative POSIX path, and source-content SHA-256.
- Added stable `NB001` and `NB002` loader errors for unsupported loading and language cases.
- Added unit tests for successful loading, rejected notebooks, defensive loader validation, and immutable loaded source models.
- Reached 100% statement and branch coverage with 98 passing tests.

### Decisions

- The loader returns notebook source models rather than `NotebookFacts`; AST analysis remains a separate component.
- Notebook format validation uses `nbformat.NO_CONVERT` so unsupported major versions are not silently upgraded during loading.
- Loader cell IDs are derived from physical source order instead of trusting optional notebook cell IDs.
- Paths emitted by the loader are relative to the selected project root when possible, with a file-name fallback outside that root.

### Open questions

- Decide whether loader errors should later be converted directly into `Diagnostic` records or remain exception-first until partial facts are available.
- Decide which notebook metadata fields beyond language and kernel should be preserved for semantic planning.

### Next step

- Implement cell-level AST analysis for supported Python code cells without resolving cross-cell dependencies yet.

## 2026-08-17 — NotebookFacts intermediate representation implemented

### Completed

- Implemented frozen, slotted dataclasses for notebook metadata, cells, statements, imports, calls, symbols, dependencies, and diagnostics.
- Added explicit enums for cell, import, symbol, and diagnostic categories.
- Enforced local and document-wide invariants at construction time.
- Implemented deterministic dictionary and JSON serialization.
- Implemented validated deserialization from dictionaries and JSON.
- Added unit and contract tests covering the complete public interchange schema.
- Reached 100% statement and branch coverage with 62 passing tests.

### Decisions

- The IR uses standard-library dataclasses rather than Pydantic for the deterministic core.
- Source facts are immutable after construction.
- Diagnostic blocking behavior is explicit and independent from severity.
- Notebook paths are relative and use POSIX separators in serialized output.
- Arbitrary nested diagnostic metadata is deferred; schema 1.0 supports immutable JSON primitives.
- Deserialization of `NotebookFacts` subclasses is rejected until an extension contract exists.

### Open questions

- Determine whether future schema versions need nested diagnostic detail values.
- Define the migration policy before publishing a second schema version.
- Decide which notebook metadata fields beyond kernel and language are relevant to semantic planning.

### Next step

- Implement the notebook loader that validates `nbformat` 4 Python notebooks and produces normalized cell source models without AST analysis.

## 2026-08-17 — Project architecture and uv tooling initialized

### Completed

- Documented the source-module boundaries, dependency direction, and test architecture.
- Defined Python, Kedro, notebook-format, and library-support compatibility levels.
- Recorded uv adoption in the first architecture decision record.
- Installed uv 0.12.5 and generated the cross-platform `uv.lock` file.
- Created the `src/` package skeleton with typed-package metadata.
- Configured Hatchling, Ruff, strict mypy, pytest, coverage, and pre-commit.
- Added unit and integration test directories with automated Iris notebook execution.
- Added a GitHub Actions matrix for Python 3.11, 3.12, and 3.13.
- Built the source distribution and wheel successfully.

### Decisions

- Python 3.12 is the primary development and strict-typing version.
- The initial compatibility matrix covers Python 3.11 through 3.13.
- The published runtime depends only on `nbformat`; ML and Kedro packages remain test dependencies.
- Kedro `>=1.5,<2` is the initial generated-project compatibility target.
- CI runs deterministic tests across the Python matrix and the complete integration suite on Python 3.12.
- GitHub Actions use a pinned `setup-uv` commit and a fixed uv version.
- Line endings are normalized to LF for source, configuration, documentation, and notebook files.

### Open questions

- Decide when Python 3.10 and 3.14 should enter the compatibility matrix.
- Define the first typed `NotebookFacts` implementation without prematurely adding Pydantic.
- Add a second file-backed notebook fixture for Data Catalog coverage.

### Next step

- Implement the immutable `NotebookFacts` domain models and their deterministic JSON serialization.

## 2026-08-17 — Reference notebook made executable

### Completed

- Replaced the nonexistent CSV input in `simple_training.ipynb` with scikit-learn's bundled Iris dataset.
- Added a deterministic, stratified train/test split and fixed model random state.
- Added a minimum accuracy assertion to make silent workflow regressions visible.
- Executed the full notebook through a real Jupyter kernel without persisting generated outputs.
- Confirmed an accuracy of `0.9` and 30 predictions on the test split.
- Updated the facts schema examples to reflect the executable data-loading cell.

### Decisions

- The first fixture uses a bundled dataset so it remains deterministic and requires no runtime network access.
- Notebook execution validation is separate from static analyzer tests, which must never execute source code.
- A later fixture will exercise file-backed input and Kedro Data Catalog generation independently.
- Future notebook-to-Kedro equivalence tests will compare observable values such as predictions and metrics, not only successful execution.

### Open questions

- Define the exact equivalence policy for floating-point metrics, arrays, and tabular outputs.
- Select the file-backed dataset and dataset format for the Data Catalog fixture.
- Decide whether executed reference outputs should be stored as snapshots or recomputed in CI.

### Next step

- Initialize the Python package and reproducible test dependencies, then automate reference-notebook execution in the test suite.

## 2026-08-16 — Deterministic analysis contract specified

### Completed

- Defined the accepted, warned, and rejected notebook constructs for the first milestone.
- Defined the versioned `NotebookFacts` interchange schema.
- Documented source provenance, symbols, calls, dependencies, and diagnostics.
- Added `simple_training.ipynb` as the first reference fixture.
- Validated the fixture as Jupyter `nbformat` 4.5 JSON.
- Verified that all Python code cells parse successfully without being executed.

### Decisions

- Static source facts will be extracted deterministically before any LLM is invoked.
- `NotebookFacts` will be the canonical typed representation and JSON interchange format.
- DataFrames may be offered as inspection views but will not be the source of truth.
- A future semantic planner will produce a separate `ConversionPlan` without modifying source facts.
- Diagnostic codes will be treated as public API once released.

### Open questions

- Choose the concrete Python model implementation: standard-library dataclasses, Pydantic, or a combination of both.
- Decide how much nested-scope detail belongs in schema version 1.0.
- Define the unsupported notebook fixtures required for each initial diagnostic code.

### Next step

- Initialize the Python package and quality tooling, then encode the documented IR as typed models.

## 2026-08-16 — English adopted as the project language

### Completed

- Translated the project documentation from French to English.
- Kept the MIT license in English.

### Decisions

- English is now the default language for documentation, source code, comments, diagnostics, commit messages, and future project artifacts.

### Open questions

- None for this documentation change.

### Next step

- Initialize the Python package skeleton and specify the first notebook fixtures before implementing the loader.

## 2026-08-16 — Project initialization

### Completed

- Clarified the target problem: automate the transition from a reasonably clean Data Science notebook to a structured Kedro project.
- Defined the initial functional scope and MVP boundaries.
- Proposed a staged architecture: loading, AST analysis, dependency resolution, intermediate representation, Kedro generation, and filesystem writing.
- Identified the primary risks: implicit state, mutations, side effects, Python scopes, parameter inference, and Kedro compatibility.
- Created `README.md` with the project context, goals, scope, and initial roadmap.
- Created this development journal.
- Initialized the local Git repository with `main` as its primary branch.
- Added the open-source MIT license.
- Created and connected the public `MipeyV/notebook-to-kedro` GitHub repository.

### Decisions

- The MVP will not depend on an LLM.
- The intermediate representation will remain separate from the Kedro generator.
- Initially, one convertible code cell will map to at most one task; automatic cell merging is deferred.
- Ambiguous cases must produce explicit diagnostics and may block generation.
- The first implementation milestone will focus on notebook analysis rather than Kedro generation.
- Generated Kedro projects will target an explicitly defined and tested version.

### Open questions

- Choose the minimum supported Python and Kedro versions.
- Define the exact matrix of supported, warned, and rejected constructs.
- Finalize the intermediate representation models.
- Choose a convention for explicit parameter extraction.
- Decide on the final project name and verify its availability before any package publication.

### Next step

- Initialize the Python package skeleton and specify the first notebook fixtures before implementing the loader.
