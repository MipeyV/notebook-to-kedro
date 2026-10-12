# Whole-notebook experiment proposal

[Documentation index](../README.md)

Status: **full experiment proposed, not implemented or measured**. The synthetic pilot's
[independent human review](synthetic-pilot-review.md) is still pending. This document defines
the remaining offline evaluation gates and the later opt-in live measurement, not a new CLI
command, automatic model injection, production feature or V2 release threshold.

The first [offline static batch increment](offline-notebook-body-batch.md) is implemented:
complete plan/graph/parameter preflight, recorded-response validation, full-slot rejection
accounting and all-or-nothing module assembly. Trusted fixed bodies execute the pilot in tests.
Reviewed notebook-bound artifacts and live measurements remain outstanding; the test-only fixture
path is not that runner.
A [draft source binding](notebook-source-binding.md) now freezes file identities and pending review
metadata, checks exact deterministic reconstruction and rejects drift before response validation.
It does not implement the approved notebook/review-bound artifact required for live measurement.
A [draft durable capture](notebook-body-capture.md) now records exclusive request reservations and
raw outcomes under that binding, with missing/unfinished inventory and offline static replay.
This is not the live collector, reviewed artifact or consent-gated behavioral worker.
A separate [draft pipeline worker](notebook-pipeline-worker.md) now executes complete valid captured
batches after explicit consent and returns bounded typed observations. It supports fresh offline
behavioral replay and caller-declared comparisons; the trusted pilot checks seventeen observables.
A [draft artifact API](notebook-pipeline-artifacts.md) now persists runtime reports and caller-declared
comparisons, records selected runtime controls before/after and refuses incompatible offline replay.
The complete experiment's reviewed-contract gate, verified model controls, durable execution/campaign
accounting and live collection remain outstanding. No prior roadmap milestone is promoted.

## Question and frozen scope

Can locally proposed node bodies preserve the entire reviewed simulation-plus-CSV workflow
when assembled into one Kedro pipeline, rather than passing isolated node examples only?

Start with the [nine-node pilot](synthetic-notebook-pilot.md), its fixed deterministic plan,
shared imports, parameter evidence, catalog and observable contract. The model proposes one
body per task; deterministic assembly supplies the reviewed interfaces and pipeline wiring.
This tests the code-proposal role, **not** LLM discovery of source loaders, task boundaries,
optimal grouping or end-to-end optimization. Keep these as separate later experiments.

The case was assistant-authored and has already appeared in development documentation.
It is not a blind holdout or representative sample of customer notebooks. Record subsequent
local provider exposure, prompt changes and manual corrections instead of calling it fresh.

## Roles and reuse

| Layer | Existing foundation | Additional evaluation work required |
| --- | --- | --- |
| Source interpretation | Notebook facts, deterministic plan and source hashes. | Bind the approved pilot review and exact plan to a whole-notebook run. |
| Code proposal | Body provider, task request and exact parameter evidence. | Request all nine bodies under a frozen run manifest. |
| Structural verification | Body assembly, strict AST/source fidelity and plan validation. | Verify complete statement coverage and assembled pipeline wiring. |
| Behavioral verification | Pilot notebook oracle, catalog loading and output observations. | Run one validated proposal pipeline in a consent-gated worker and compare all observables. |
| Evidence | Node-corpus capture/replay and artifact publication patterns. | Define a separate notebook-bound envelope and interrupted-run inspection/replay tests. |

Existing node benchmark loaders require approved node/behavioral corpus contracts; they do
not accept `pilot-draft-1`. Do not pass this fixture to those CLI commands or reclassify its
nine tasks as nine independent notebook successes. Reuse implementation patterns and public
validation APIs without weakening their schemas or mutating historical artifacts.

A later LLM **structureur** can issue source/proposal comparison diagnostics. Its verdict is
advisory: neither it nor the codeur can approve its own source reference, override AST rejection
or replace runtime checks. No fine-tuning or second trained model is needed for this first
measurement; evaluate role-specific prompts separately before deciding whether training helps.

## Gates and order

1. Complete and record human source/catalog/contract review. Review corrections require a new
   identified revision and regenerated baseline; do not reuse prior outcomes as current evidence.
2. Implement the notebook-bound report, fake-provider flow, worker and replay **offline**.
   Development tests may use the pending draft only if they retain its unapproved status and
   do not produce approved benchmark scores. No live calls while the review gate is pending.
3. Reproduce the source notebook and deterministic baseline in the same locked runtime.
   Confirm all six oracle sensitivity controls before a proposal measurement.
4. Freeze model/runtime identity, requests, prompt/validator/assembly versions and budgets.
   An operator explicitly opts into local provider I/O and untrusted code execution.
5. Request each of nine bodies once. Persist raw responses before parsing; preserve every
   provider error, schema failure and static rejection. No repair, retry or fallback substitution.
6. Assemble an evaluation-only project if and only if all nine proposals pass static checks.
   Execute its complete DAG with the real CSV catalog and compare against both the source
   notebook and the separately reviewed expectations. Never patch the user's project.
7. Replay the same raw evidence without provider I/O, with renewed execution consent and
   compatible source/runtime controls. Report replay separately from live latency.

## Preflight and run identity

The implementation must refuse a live run before provider I/O when review evidence is absent,
source hashes differ, plan validation fails, parameter evidence is ambiguous, destination
already exists, capture is unavailable, or explicit execution consent is missing.

Record at least:

- Notebook, CSV, reviewed contract and expected-catalog identities; reviewed commit/evidence.
- Exact nine requests and task/cell/statement mapping; ordered inputs/outputs, shared imports,
  catalog and parameters. Hash the canonical plan rather than trusting node names alone.
- Prompt, body schema, assembly, parameter evidence and static validator versions.
- Package commit, lockfile hash, Python and relevant library versions, OS and hardware.
- Local model name and digest, Ollama version, loopback base URL, generation settings and
  effective context/budget information when available. Unknown values stay explicitly unknown.
- Proposed limits: one request per task, provider timeout `120` seconds per request and
  complete-pipeline worker timeout `60` seconds, with actual limits recorded in the manifest.
  Final byte/capture limits must be chosen and tested before live use, not left unlimited.

Start with one already installed local model in body mode and one complete attempt; do not
download models or select a claimed best model automatically. The cap is nine inference calls,
not zero local compute cost. Model metadata queries are recorded separately from inference.
Full-code comparison, repeated attempts and a second model are later explicit configurations;
do not select the best successful attempt retrospectively or overwrite earlier attempts.

Only loopback Ollama is in scope. No paid API, account, remote notebook upload, tracker,
dataset download or automatic cloud credential handling. User-controlled isolation is needed
for untrusted execution: a timeout/subprocess is fault containment, not an OS security sandbox.
Observing intermediate frames and the fitted model must not require loading untrusted pickles
in the parent process; return bounded, typed JSON observations from the worker.

## Evidence and outcomes

Design a separate versioned envelope with manifest, exact raw responses/errors, parsed bodies,
validation diagnostics, assembled-code identities and one complete-pipeline outcome. Publish
exclusively into an ignored, private destination. Capture raw evidence atomically before parsing
or execution; preserve partial progress on interruption without inventing a completed report.
Capture write failures abort the run. Hashes establish content identity, not trusted authorship.

Use explicit states for requests not made, provider errors, invalid responses, static rejection,
pipeline not executed, execution failure, timeout, observation failure, behavioral mismatch and
match. Independent mismatches retain dataset/output names and differences within byte limits.
Never claim runtime equivalence from static acceptance alone or treat missing output as a match.

| Metric | Denominator and interpretation |
| --- | --- |
| Planned requests | Always nine; show how many were attempted and retain missing slots. |
| Static acceptance | Accepted proposals / nine, including failures and unrequested slots. |
| Complete static readiness | One pipeline only if all nine bodies and wiring are valid. |
| Complete behavioral success | Matching complete pipelines / all registered attempts; this pilot contributes one notebook per attempt. |
| Observable checks | Report each required table, series, model, split, prediction and metric as match, mismatch or not evaluated. |
| Latency | Separate proposal phase, complete worker execution and whole-run elapsed time; replay is not inference latency. |
| Corrections | Original attempt stays frozen; any human fix is a separately identified corrected artifact, not a model success. |

For an all-node static failure, behavioral checks are **not evaluated**, not nine partial
pipeline successes. For an interrupted attempt, retain it in the attempt inventory as incomplete
and withhold a completed benchmark score; any campaign summary must disclose all such attempts
and count only fully matching attempts as successes. Do not report success only among survivors.
Do not compare these notebook-level denominators with earlier 17/17 node-scenario results.
The six trusted negative controls measure oracle sensitivity, not six additional model cases.

## Offline acceptance before live use

- A fake provider is called once for each planned task, without Ollama/network I/O.
- Exact reference bodies yield the same catalog, nine-node DAG and all expected observations
  as the notebook/baseline; label this reference compatibility, not model accuracy.
- Each provider/schema/static failure is retained; a single rejected body prevents complete
  pipeline execution and does not trigger deterministic replacement of that node.
- Wrong source/review identity, missing consent and capture failure prevent inference or execution
  at the relevant preflight gate. No proposal is executed before complete static validation.
- Trusted semantic mutants demonstrate table/schema/alignment sensitivity using the existing
  test-only oracle path; never relax production AST fidelity to admit these negative controls.
- Worker timeout, malformed/oversized observation and execution exceptions have distinct outcomes.
- Interrupted evidence can be inspected; replay validates exact identities and renews consent,
  makes zero provider calls and recomputes outcomes rather than trusting cached observations.
- The default converter, historical corpora, prompts and validators remain unchanged.

Fresh-environment installation and a separate `kedro run` process remain additional packaging
gates, not prerequisites silently claimed by this locked-runtime experiment. Broader loader
contracts, adaptive templates, enterprise logging and optimization follow the
[product vision](../product/product-vision.md), not this fidelity-only protocol.
