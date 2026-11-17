# Prepared coding-agent versus converter comparisons

[Documentation index](../README.md)

Status: observed on 2026-11-17. These are user-requested external coding-agent experiments,
separate from product model providers and the pending whole-notebook pilot review.

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
