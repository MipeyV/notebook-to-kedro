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
