# Synthetic banking and insurance conversion cases

[Documentation index](../README.md)

Status: two synthetic case definitions and selected-runtime measurements, 2026-11-20.
The [corpus guide](../../examples/banking_insurance/README.md) documents data roles, generator,
commands, temporal cohorts, costs and limitations. All records are invented. No financial-mdl
data, personal records, external model provider or real portfolio execution is involved.

## Frozen inputs and scope

| Case | Rows | Target | Positive rows | Train / validation / test / embargo |
| --- | --- | --- | --- | --- |
| Credit | 4,200 | Default event within 12 months | 394 | 1,800 / 600 / 600 / 1,200 |
| Insurance | 5,040 | Lapse within 12 months | 514 | 2,160 / 720 / 720 / 1,440 |

Each case has 12 predictors, missing values, imbalanced targets, temporal shifts and a new
test-only channel category. Individual data dictionaries and manifests distinguish as-of
features from identifiers, future metadata and labels. All main observations have complete
12-month follow-up; incomplete windows occur in a separate guard fixture and are not relabeled
as negatives. The binary lapse target excludes competing-risk/survival modeling.

Ten procedural cells perform loading/guards, temporal partitioning, feature selection,
training-only imputation, training-vocabulary dummy encoding, forest fitting, validation-only
threshold selection, test scoring, metrics and reporting. Training uses 2018-2020, validation
2022 and test 2024. The 2021/2023 embargo cohorts prevent outcome-window overlap. The recognized
forest seed/tree-count arguments become two parameters; other business assumptions remain
unchanged source constants. The final scored table stays in memory.

The [measured snapshot](../../examples/banking_insurance/observations.json) binds notebook,
dataset and regression hashes and records the actual runtime versions. Main CSVs and notebook
JSON use LF attributes so these identities survive checkout. Dataset generation is deterministic
and does not execute a notebook or capture model outputs as expectations.

## Acceptance checks

- Source accounting must be complete for the working layouts, with ten generated nodes.
- Original sequential notebook code and the registered Kedro pipeline must match every leaf
  output, including the scored table, under default/custom profiles and Sequential/ThreadRunner.
- Binary metrics are recomputed independently with counts, pairwise AUC and grouped-score
  average precision. Threshold selection is independently checked against the declared grid
  and illustrative validation costs. The metric calculations do not call sklearn metrics.
- Flipping holdout labels must leave learned medians/modes, model scores and the selected
  threshold unchanged. Extreme holdout predictor values must not change fitted preprocessing
  or the validation-selected threshold.
- Each generated project must pass its ten shipped tests and an actual Kedro CLI invocation.
- Inverting generated test scores must break the source/Kedro comparison.
- Known unsupported layouts must remain blocked before publication.

The shipped suite supplies deterministic cohort/feature expectations, one hand-computed metric
node case and exact empty/duplicate/incomplete/invalid-target failures. Full model-score vectors
are absent from golden expectations. Missing positive model/node/output expectations remain
visible in `regression-coverage.json`; generated tests do not infer scientific acceptance.

## Measured outcome and modeling limits

The selected Windows Python 3.12.14 run used Kedro 1.5.0, pandas 2.3.3, NumPy 2.5.2 and
scikit-learn 1.9.0. Eight source/Kedro pairs matched all leaf outputs. The 16 integration checks
also passed the four delivered-suite/CLI combinations (ten shipped tests each), holdout
isolation checks and both deliberate score inversions. These checks reuse locked development
dependencies. The new business cases are not added to the separate six-variant fresh-install
bootstrap, and their runtime evidence is not a three-version installation claim.

| Test-cohort metric | Credit | Insurance lapse |
| --- | --- | --- |
| ROC AUC | 0.52661424 | 0.60451034 |
| Average precision | 0.10600630 | 0.13575934 |
| Brier score | 0.23900605 | 0.22765269 |
| Selected threshold | 0.15 | 0.65 |
| Recall | 1.00000000 | 0.05797101 |
| Alert rate | 1.00000000 | 0.03888889 |
| Illustrative test cost | 541 | 284 |

Conversion fidelity passed; predictive usefulness is not established. Credit discrimination is
weak and the declared validation cost selects an all-alert test policy. The lapse test cost
284 is worse than the no-alert baseline cost 276 under the demonstration weights. The credit
no-alert baseline would cost 708; its all-alert result reflects the declared trade-off, without
an operational capacity constraint. These unfavorable observations are retained without tuning
the data, model or threshold grid after inspecting test results. Scores are uncalibrated and
the simulation is not fitted to empirical banking/insurance distributions. No fairness,
regulatory, economic-value or human-productivity conclusion follows.

## Preserved conversion boundaries

The first draft exposed an assertion-only mixed cell that the planner cannot claim as a task.
`boundary_assertions.ipynb` retains that layout and is blocked with SA002. Its concatenated Python
AST is identical to the working layout, whose initial guards and preparation share one cell.

A later use of the raw catalog for a reporting row count triggers SA008: the converter refuses
to risk reloading the source across tasks. `boundary_catalog_reuse.ipynb` retains this case.
The working notebook explicitly materializes the original row count during preparation.
Both refusals are tested on both domains, including absence of a published destination.
No engine, AST-fidelity or source-accounting rule changes in this increment.

The additional fixtures broaden supported-case evidence and expose authoring constraints;
they do not establish arbitrary procedural notebook support, aliased/multi-file workflows,
production risk scoring or automatic business-parameter inference.
