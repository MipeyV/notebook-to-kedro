# Prepared coding-agent versus converter comparisons

[Documentation index](../README.md)

Status: observed on 2026-11-17. These are user-requested external coding-agent experiments,
separate from product model providers and the pending whole-notebook pilot review.

The first sections retain the supported-case batch. A later [boundary-focused batch](#boundary-focused-extension)
adds larger and deliberately unsupported inputs, including all blocked outcomes. They have different
selection criteria and must not be pooled into a general conversion success rate.

## Scope and common acceptance

Following the earlier [two-node scalar check](../reference/local-operations.md#one-prompt-agent-check),
three additional synthetic tasks exercised implemented functional conversion boundaries. The
[data-only corpus](../../examples/agent_comparison/README.md) preserves source/configuration/oracles,
acceptance requirements and portable prompt templates. Its observations.json records aggregate
outcomes and inventories. Detailed candidate projects, transcripts/logs and the experiment-specific
coordinator checker remain ignored locally; no benchmark API or live campaign runner is added.

Each task supplied the same source, explicit workflow settings, naming profile and regression
expectations to both methods. The environment was already provisioned. Three fresh-context coding
agents ran concurrently, with one detailed prompt each and no corrective coordinator follow-up.
Agents could use the generic shared writer for their own authored files; converter analysis,
planning, transformation and test-rendering APIs and other solutions were excluded. Exact agent
model identifier, token count and cost were not exposed. Prompts included the same contained-temp
directory and current Kedro catalog API guidance learned from the earlier scalar experiment.

Independent acceptance loaded actual project registries/catalogs and checked helper ASTs, declared
parameters, prefixed node names, source-order dependencies, assign-mode memory intermediates,
copied JSON inputs and persistent JSON reports. It exercised three pipeline oracles per case,
every supplied JSON node oracle, a ThreadRunner run, standard Kedro CLI, delivered pytest suites
and a source arithmetic mutation in separate private copies. Both canonical candidate inventories
and frozen inputs remained unchanged during coordinator acceptance. No coordinator repaired a
candidate project. Package/resource files also had to remain byte-identical under their original
import namespace. Intentional mutations were rejected through test assertions, without setup errors.

The package case supplies three pipeline expectations, with no JSON node expectations for its
dataclass intermediate. That existing typed-oracle gap remains explicit; extra agent-owned typed
tests do not establish a generated typed-test capability.

## Observed outcomes

All six candidates passed the common independent acceptance on the first coordinator attempt.

| Case | Added scope | Agent production window, approximate | Converter in-process production | Delivered tests passing, agent / converter |
| --- | --- | --- | --- | --- |
| ml-notebook | Unexecuted functional notebook; NumPy preparation, scikit-learn linear fit/predict and MAE; three nodes | 207.4 s | 0.435 s | 16 / 12 |
| ordered-join | Independent JSON loaders, normalization, flat candidate mapping and joined result; four source-ordered nodes | 234.0 s | 0.399 s | 21 / 15 |
| package-resource | Original local package, relative imports, dataclass intermediate and package-relative JSON resource; two nodes | 193.8 s | 0.422 s | 7 / 3 |

| Case | Common acceptance, agent / converter | Failing delivered tests after the same arithmetic mutation, agent / converter |
| --- | --- | --- |
| ml-notebook | 10.697 s / 11.291 s | 9 / 6 |
| ordered-join | 4.830 s / 5.791 s | 10 / 6 |
| package-resource | 4.943 s / 5.402 s | 6 / 3 |

The new cases total nine independent pipeline expectations and 21 JSON node expectations per
method. Delivered suites passed 44 agent tests and 30 converter tests. Additional agent tests
cover threading, graph/source/identity contracts; raw test count is not a quality ranking. The
ML report preserves rounded predictions and MAE defined in the original source; no source repair
or tolerance relaxation was introduced for comparison.

The ML and package agents initially passed string keys to the generic publication writer, which
requires Path keys. Both retained the failure, corrected their authoring script and then passed
tests. The join agent required no implementation correction. Agent-owned mutation checks in the
join/package cases temporarily changed their own candidates and restored original bytes before
completion; the coordinator independently checked fresh copies afterwards. Intentional mutation
failures and initial access/publication failures remain in local evidence. All three converter
lanes completed inspect/plan/generate without corrections.

## Timing boundaries and limits

Agent production windows run from a one-second coordinator UTC reference immediately before
dispatch to the agent-recorded UTC completion. They include authoring, source/spec reading, tool
and service scheduling, internal corrections, tests, CLI and mutation self-checks. Dispatch is
approximate rather than a model inference timer. Later coordinator-observed completion windows
are separately retained in observations.json: 221 s, 254 s and 238 s respectively. Agents ran
concurrently on the same host; these are observations, not controlled service latency estimates.

Converter timing uses perf_counter after interpreter entry, including imports, input/configuration
loading and measured inspect/plan/generate. It excludes interpreter startup and the separately
reported common acceptance. Source/configuration/oracle preparation and human review were not
timed prospectively for either method. The common acceptance adds actual CLI, delivered tests,
independent sequential/threaded behavior and mutation checks; it is not included in the subsecond
production figures. No direct speedup ratio or saved human interval is inferred.

The observations confirm lower converter production latency on these supported, preconfigured
tasks, while both approaches meet the same acceptance. There is one attempt per method/task,
no repeated-run distribution, randomization, cost record, manual baseline or independent human
acceptance. No wheel build, installation or dependency resolution was performed for these three
cases. The reused locked environment reports Kedro 1.5.0, kedro-datasets 8.1.0 and Python 3.12.14;
the aggregate data also records installed NumPy/scikit-learn/pytest/nbformat versions.

The notebook contains explicit supported functions and no executed outputs. It is not an arbitrary
procedural-notebook comparison or the separate nine-task whole-notebook LLM pilot. No financial
source/data/runtime or broader pilot approval was used. The next comparison should include larger
and unsupported inputs plus prospectively observed configuration, corrections and review. Preserve
blocked outcomes instead of treating quick refusal as successful conversion.

## Boundary-focused extension

On the same date, the user authorized larger, less-clean and unsupported cases. A new
[data-only challenge corpus](../../examples/agent_comparison/challenges/README.md) preserves three
frozen sources, workflow/profile/expectation files and portable prompts. Existing supported-case
inputs and observations remain unchanged. Engine commit 54a24873baf71f2fd1663d732cc4d31394a92e54
was unchanged throughout this batch; no limit, source rule, expectation or input was relaxed.

Three fresh agents again received one prompt each, ran concurrently in the ready environment and
received no corrective coordinator hints. All three agent projects passed independent acceptance.
All three tool conversions were blocked and published no project. Those tool intervals end in
refusal, so there is no successful-conversion speedup comparison for this batch.

| Case | Frozen task | Agent outcome / approximate production window | Tool outcome |
| --- | --- | --- | --- |
| larger-ml-notebook | Eight steps, 74 source lines, 142 raw records reduced to 140 pairs, 100 training/40 holdout rows, three scenarios and 24 node expectations | Passed / 254.0 s | Inspection passed; planning/generation rejected the regression contract above 64 KiB |
| messy-control-flow | Three helpers with loops/conditionals, clipping/missing-value errors, stale saved notebook output and nonmonotonic execution counts | Passed / 212.9 s | Inspection blocked by straight-line helper restrictions; planning/generation failed |
| shared-mutable-fanout | Four calls with one buffer consumed twice, ordered mutations and source identity assertions | Passed / 230.9 s | Inspection passed; planning/generation rejected aliasing/fan-out |

| Case | Independently passing delivered tests | Independent acceptance | Tests failing after the arithmetic mutation |
| --- | --- | --- | --- |
| larger-ml-notebook | 42 | 13.627 s | 10 |
| messy-control-flow | 23 | 7.049 s | 10 |
| shared-mutable-fanout | 14 | 5.626 s | 10 |

Independent checks covered all nine pipeline expectations and 33 supplied JSON node expectations,
ThreadRunner behavior, standard Kedro CLI, preserved helper ASTs, source-order graph dependencies,
exact defaults/catalogs, candidate-contained inputs and arithmetic mutations on private copies.
The messy case additionally preserved both ValueError messages and published no report for those
failed invocations. The fan-out case additionally ran the actual registered nodes and verified both
consumer outputs reference the identical buffer, with exactly left/right events in source order.
No JSON per-node contract was invented for its reference-sensitive intermediate. Candidate/input
inventories remained unchanged during coordinator acceptance. All 79 delivered tests passed.

The larger case exposed an unanticipated fixture-size boundary, rather than a large-data benchmark:
its original regression JSON is 358,514 bytes and lossless whitespace compaction is still 81,334
bytes, above the existing 65,536-byte loader budget. The [documented contract limit](../reference/generated-workflow-tests.md)
remained intact. The coordinator initially expected this case to be supported; its outer preflight
assertion failed after retaining all attempts and the blocked result. No contract was compacted,
split, trimmed or removed to produce a passing conversion. Source inspection passing alone does
not establish end-to-end eligibility.

Raw engine evidence retains one blocked inspection, two successful inspections and all six failed
plan/generate operations. Control-flow diagnostics include BL004/BL006, and generation errors
remain LO002 with their original messages. In-process attempt totals were 0.320 s, 0.332 s and
0.321 s respectively. No runtime acceptance was run for the tool because no project existed.
These are failure/coverage observations, not faster accepted projects or saved human time.

Agents passed their first publication/tests/CLI checks without candidate corrections. Initial
default-token prompt-access failures were retained; the fan-out agent also corrected an unsupported
PowerShell UTC probe before authoring. Intentional mutation copies/failures remain in local logs.
The exact model identifier, token cost and prospectively measured human preparation/review remain
unavailable. Agent intervals use the same approximate pre-dispatch UTC reference to agent-recorded
completion convention; coordinator-observed windows are also retained separately (281 s, 228 s,
250 s). Independent acceptance time remains separate. No build, installation, dependency resolution,
financial source/data/runtime or separate whole-notebook pilot approval was involved.

This batch intentionally probes boundaries and has one attempt per method/case. It establishes
three agent successes and three tool blockages on these tasks, not general accuracy estimates.
Together with the earlier supported batch, it distinguishes fast prepared conversion from broader
source coverage. Concrete follow-up candidates are bounded fixture-backed regression contracts,
preserving control flow inside called helpers, and an explicit shared-data/source-order contract.
Dynamic orchestration and mutable identity must retain separate acceptance evidence; no fallback,
automatic repair or new capability is implemented by this report.

## Fixture-backed follow-up on 2026-11-18

The original blocked batch and its frozen corpus/observations remain unchanged. A subsequent
engine increment adds [regression schema 1.1](../reference/generated-workflow-tests.md#scenario-fixtures-in-schema-11),
which captures bounded pinned scenario files separately from the manifest. A new local copy of
the eight-step case uses this format; source and resolved expectation values match the original
exactly. This is a new declaration, not a reinterpretation of the old oversized 1.0 attempt.

The new manifest is 464 bytes with 287,792 fixture bytes. Inspect/plan/generate completed, and
independent acceptance passed source/default/catalog/order checks, all three pipeline and 24 node
expectations, ThreadRunner, the standard Kedro CLI, 27 shipped tests and the original arithmetic
mutation (six assertion failures, no setup errors). Canonical candidate/input inventories remained
unchanged during acceptance. Configuration loading plus three measured operations took 0.175 s
in-process after imports/preparation; independent acceptance took 8.470 s. Preparation/review and
startup were not timed, and no human saving or direct ratio against earlier agent clocks is inferred.

Fixture source paths, hashes and generated destinations are reviewable in the new report. Local
projects/logs stay ignored. The original inline declaration still exceeds its unchanged 64 KiB
limit. Loop/conditional helper and mutable-fan-out cases remain blocked; neither was repaired or
reclassified by the fixture format. No new agent call, installation, financial runtime or separate
whole-notebook pilot approval was used for this follow-up.

## Preserved-helper follow-up on 2026-11-18

A separate engine increment now retains structured if/for/while inside function bodies without
rewriting their ASTs or allowing conditional/iterative orchestration. A new local copy of the
original messy-control-flow case keeps every original input/configuration/expectation byte.
Inspect/plan/generate now complete. Configuration loading and the three operations took 0.088 s
in-process after imports/preparation; this does not measure human effort or whole-journey time.

The unchanged independent checker confirms source AST/default/catalog/order, three normal
pipeline/nine node oracles, both original ValueError messages with no failed-invocation report,
ThreadRunner, the standard Kedro CLI and 12 passing shipped tests. It then retains its original
failure: the comparison required at least 14 shipped tests. That criterion was not lowered and
this is not a fully accepted original comparison outcome. The finite-JSON contract has no explicit
failure expectations; the two source error paths are independently validated, not generated as
exception tests. Private logs retain this delivery gap rather than replacing the failed record.

Separate repository tests compare original functions with registered pipelines across both source
formats, profiles and sequential/threaded runners, including call order, intermediate identity
and exact exception type/arguments. Shipped 12-case suites detect the original arithmetic mutation
with six assertion failures. Additional while/break/continue/else runner cases check retained
behavior. Analysis imports/executes no application or notebook cells. A paired public example is
available at examples/functional_control_flow; the frozen original corpus remains unchanged.

Known blockers include early/multiple returns, try/with/match, deferred/dynamic constructs,
mutation writes and source fan-out. Conservative post-loop bindings can reject valid functions
unless locals are preinitialized. Paths, iteration counts and termination are unverified. No
additional agent call, install, financial runtime or separate pilot consent was involved. Explicit
exception-test expectations and shared mutable data remained separate follow-up scopes at that
revision. The exception increment is recorded below; shared mutable data remains unsupported.

## Explicit-exception follow-up on 2026-11-18

A new run keeps every original messy-control-flow input byte and the independent checker's
minimum_tests=14 unchanged. Separate supplementary settings select regression schema 1.2 with
the same three positive pipeline/nine node expectations and the two frozen failure scenarios.
Each failure explicitly declares ValueError, the original literal message and its failing step.
No expected value or failure was inferred from an execution. The earlier blocked and 12-test
records above remain unchanged.

Configuration loading plus inspect/plan/generate took 0.113 s in-process after imports/preparation.
The unchanged independent checker passed in 6.016 s, including source AST/catalog/parameter/order
checks, three positive cases with nine node oracles, both failure paths with no final report,
ThreadRunner, Kedro CLI and all 14 shipped tests. The original arithmetic mutation produced six
assertion failures, with eight remaining tests passing and no collection/runtime errors. Canonical
project and original inputs remained unchanged by acceptance.

Repository integration controls exercise script/notebook, default/custom profiles and inline/
fixture storage. Wrong concrete type (including a subclass), literal message, failing node,
absent exception, final-output publication, catalog setup and registry errors cannot satisfy an
exception expectation. Node failures and fixture header validation have separate controls.
No further agent call, financial execution, installation or pilot authorization was used. These
prepared synthetic clocks establish neither human saving nor representative conversion accuracy.

## Explicit shared-data follow-up on 2026-11-18

A new local run preserves every original shared-mutable-fanout input byte and the unchanged
independent checker's minimum_tests=4. Supplementary workflow settings explicitly declare the
buffer intermediate as shared. The three original pipeline oracles remain unchanged; a separate
constructor node oracle is transcribed from the original literal return, giving four shipped
tests. That declaration/preparation effort is outside the measured production interval. No
business expectation is inferred by the engine or collected from execution.

Configuration loading plus inspect/plan/generate took 0.091 s in-process after imports/preparation.
Independent acceptance passed in 5.599 s: original helper ASTs, catalog/parameters, four singleton
ordered groups, actual registered-node shared identity and left/right mutation trace, all three
pipeline cases, ThreadRunner, Kedro CLI and four shipped tests. The original arithmetic mutation
produced three assertion failures, one passing constructor test and no errors. Canonical project
and original inputs remained unchanged by acceptance. Original blocked observations are retained.

Repository checks exercise paired script/notebook input, default/custom profiles and both
SequentialRunner/ThreadRunner, including intermediate/nested identity, unchanged source results
and stop-on-error without retry. Replacing assign storage with deepcopy breaks the source identity
assertion. Removing the left-to-right dependency deterministically permits the wrong mutation
order under ThreadRunner. Duplicate arguments in one call can explicitly share one intermediate.
API/CLI/local generation stay static and use the existing writer; no new provider, financial run
or pilot authorization is involved.

This contract covers declared intermediate references within one process, not general DAG
inference, shared catalog inputs/parameters, process runners or arbitrary concurrent mutation.
JSON cannot express aliases between independent node arguments, so three node-oracle gaps remain
explicit. The three frozen boundary cases now have separate accepted prepared follow-ups; this
does not revise the original blocked batch or establish representative success/human productivity.
