# Nested financial model conversion evidence

[Documentation index](../README.md)

Status: selected synthetic composition cases measured on 2026-11-20. The
[corpus guide](../../examples/nested_financial/README.md) defines the source, temporal folds,
commands and runtime boundaries. All datasets are byte-identical copies of the original
synthetic banking/insurance portfolios; original notebooks and results are unchanged.
No private financial-mdl data, external model provider or real portfolio is involved.

Follow-up, 2026-11-21: the [SA009 guard](../reference/source-accounting.md#fitted-pipeline-aliases)
now blocks the original fitted-alias layout before project publication. The source, data,
regression files and measured snapshot below retain their original identities and observations.
Current tests verify refusal through API, CLI and local operations while the working cases
retain their runtime/CLI/component checks. The historical account below describes the earlier
measurement, including the two then-statically-complete runtime boundaries.

A separate 2026-11-21 [model output slice](../reference/model-outputs.md) adds opt-in versioned
storage and selected-runtime reload checks for the unchanged working notebooks. That evidence
is separate from the original memory-only snapshot, which is not rewritten to claim persistence.
The existing six-variant fresh-install bootstrap is unchanged.

## Acceptance and observations

Two nine-cell notebooks exercise ColumnTransformer, nested preprocessing Pipelines, logistic
regression, soft voting and temporal calibration. The inner estimators remain inside the
training node; no new engine rule or sklearn graph inference is introduced.

The [measured snapshot](../../examples/nested_financial/observations.json) binds source, data
and regression hashes and records dependency versions. Eight source/Kedro pairs match every
leaf output under default/custom profiles and SequentialRunner/ThreadRunner. The fitted-model
comparison checks validation/test probabilities and fitted medians, modes, categories and
scaler means against the actual training subset for each fold. Independent checks recompute
binary metrics/thresholds, soft-vote averages and calibrated-fold averages. Calendar assertions
check both the internal calibration gap and the outer validation separation.

Eighteen integration tests also exercise ten shipped regressions and an actual Kedro CLI run
for each case/profile, both boundary variants and deliberate changes to logistic regularization
or vote weights. Those changes must break prediction parity. Generated tests have no model
object or full probability-vector oracle; missing expectations remain explicit.

| Test-cohort observation | Credit pipeline | Calibrated lapse vote |
| --- | --- | --- |
| ROC AUC | 0.56599518 | 0.63389657 |
| Average precision | 0.12565070 | 0.14416055 |
| Brier score | 0.08872582 | 0.08741345 |
| Validation-selected threshold | 0.15 | 0.50 |
| Recall | 0.10169492 | 0.00000000 |
| Alert rate | 0.09333333 | 0.00138889 |
| Illustrative test cost | 686 | 277 |

These are selected Windows Python 3.12 measurements with the locked development environment,
not fresh-installation evidence for these new cases. The six-variant bootstrap matrix remains
unchanged. The lapse case still costs more than the no-alert baseline (276) and catches no
test positives at the selected threshold. Calibration machinery and a lower Brier score do not
establish calibration quality or economic usefulness. No data, model or threshold was tuned
after inspecting these test results. Original baseline results remain preserved separately.

## Measured installation journeys

Follow-up, 2026-11-22: `tools/check_financial_journey.py` composes the existing local operations,
model-output declaration and notebook schema 1.1 tests. The two original working notebooks are
copied unchanged into new workspaces. Both naming profiles are exercised. This is an opt-in
developer journey; analysis/generation remain static and no private financial-mdl code or data
is used.

An explicit reference subprocess executes the original notebook and selects validation positions
0, 1, 2, 3, 100, 200, 300 and 400 without using predictions or targets to choose rows. It serializes
those feature rows to CSV, reloads that representation and captures predict/predict_proba values.
These are source-derived regression references, not independent scientific expectations or
held-out performance estimates. Full estimator state remains outside the generated contract.

The journey creates a new settings file and explicit regression contract through the shared
writer. Existing operation measurements cover inspect, plan and generate; the exact file/copy
preview must match publication. Each generated wheel is installed with its test extra in a fresh
venv without system packages or the converter. Seven known runtime packages (NumPy, pandas,
SciPy, scikit-learn, Kedro, kedro-datasets and pytest) match the reference interpreter via an
explicit constraints file. Other dependencies resolve normally. This is neither automatic
dependency inference nor unconstrained/cross-version portability evidence.

Twelve delivered tests run from copied configuration/data/tests with an empty src directory.
Ordinary `python -I -m kedro run` then saves one model version. A new process reloads that exact
version and checks both reference probes; hashes must remain unchanged. A separate runtime copy
inverts the supplied labels and reverses probability columns. Both selected reload tests must
fail with the fresh-process comparison diagnostic, rather than an import/setup failure. Original
source, generated project, input/configuration/test files and CLI-saved model bytes are protected
by postflight identities.

The separate [journey snapshot](../../examples/nested_financial/journey-observations.json) records
the selected Windows Python 3.12 results and timing scopes. The first engineering attempt failed
after generation because its effort form used an unsupported setup-mode label; no installation
ran and the remaining case was not attempted. Its local evidence is retained. A subsequent
two-case default run passed, followed by the four-profile-case run recorded in the new snapshot.
The original observations.json and unfavorable model results above are unchanged.

| Selected Windows run | Total case elapsed | Inspect + preview + generate |
| --- | --- | --- |
| Credit, default | 41.54 s | 0.142 s |
| Credit, custom | 45.45 s | 0.262 s |
| Lapse, default | 46.20 s | 0.320 s |
| Lapse, custom | 46.77 s | 0.244 s |

These are prepared-case machine observations. New venvs can reuse uv's package/download cache;
this is not a cold-machine benchmark or a representative user-effort comparison.

Machine evidence includes reference execution, workspace preparation, operation timings,
build/install/test/CLI/reload/control subprocess durations and total case elapsed time. These
scopes overlap: preparation and subprocess times are included in total elapsed time. They must
not be added to that total. Human configuration, adaptation, correction and review remain
unmeasured. The existing effort-comparison kit emits pending declarations; savings and baselines
stay null. Prepared sources and source-derived references do not represent an unassisted first use.

The generated JOURNEY.md links the configuration usable in VS Code, the full preview and the
installation/evidence artifacts. The harness calls the same local operations as the extension;
it does not exercise or time a person's UI interaction. CI runs these four fixed journeys in a
separate Python 3.12 job and retains partial evidence on failure. The existing six-variant
bootstrap is unchanged. Broader libraries, independent prospective user trials and scientific
acceptance remain separate work.

## Static completeness and runtime failures

The fitted-alias boundary succeeds in the original source and fails in Kedro with an unfitted
ColumnTransformer. Default memory copies isolate the preprocessor prototype from the fitted
model-owned component. This exposes a conversion fidelity gap despite complete static accounting.
The main credit notebook explicitly uses its model-owned component; the converter does not
automatically repair aliases or change storage to assign mode.

The stacking boundary fails in both source and Kedro with the same sklearn partition error.
This is a preserved library failure, not a successful temporal stacking model. Changing its CV
would change the source's scientific assumptions and is outside faithful conversion. The main
calibrated vote is a distinct authored example, not an automatic rewrite of the stacking source.

Source accounting, AST fidelity, runtime dependency surface and publication contracts are
unchanged. Arbitrary model nesting, process runners, estimator persistence, general alias
semantics and representative productivity measurements remain outside this evidence.
