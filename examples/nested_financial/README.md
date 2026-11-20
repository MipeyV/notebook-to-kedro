# Nested banking and insurance models

These authored procedural notebooks reuse the byte-identical seed-42 portfolios from
[banking_insurance](../banking_insurance/README.md). Records, labels, feature roles, temporal
cohorts, failure fixtures and illustrative costs are unchanged. All records are invented.
The original forest cases and their unfavorable results remain separate baselines.

| Case | Estimator composition | Outer Kedro graph |
| --- | --- | --- |
| [Credit pipeline](credit_pipeline/workflow.ipynb) | ColumnTransformer with numeric imputation/scaling and categorical imputation/encoding, followed by logistic regression inside a Pipeline | Nine nodes; no recognized candidate parameters |
| [Lapse calibrated vote](lapse_calibrated_vote/workflow.ipynb) | CalibratedClassifierCV wrapping a preprocessing Pipeline and a soft VotingClassifier containing logistic regression and a small random forest | Nine nodes; two recognized nested forest parameters |

Nesting remains inside the authored training node. The converter preserves source code and
wiring; it does not flatten sklearn's internal estimators into separate Kedro nodes, infer
their semantics or choose a model. The final `fitted_model` is an in-memory output. There is
no durable estimator serializer or generated model-object comparator.

## Temporal fitting

Both workflows train on 2018-2020, select a decision threshold on 2022 and score 2024, retaining
2021/2023 embargo years. Identifiers, future metadata and targets stay outside the predictors.
Numeric medians/scaling and categorical modes/vocabularies are learned from training only.
Unknown holdout categories are ignored by the encoder; no holdout vocabulary is fitted.

The lapse workflow uses three expanding TimeSeriesSplit folds on the 2,160 training rows,
with 360 calibration rows and a 720-row gap per fold. Fold training sizes are 360/720/1,080.
The gap interpretation relies on this corpus's uniform 60 rows per month. Tests verify actual
dates: training outcome windows finish before calibration snapshots, and calibration outcome
windows finish before outer validation snapshots. This is not a general calendar-purge policy.
With `ensemble=True`, each clone is fitted on its fold's training data and calibrated on its
calibration data; the three calibrated predictions are averaged. See
[CalibratedClassifierCV](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html)
and [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## Generate and verify

From the repository root, with new output directories:

```bash
uv run notebook-to-kedro project plan examples/nested_financial/credit_pipeline/project.json
uv run notebook-to-kedro generate examples/nested_financial/credit_pipeline/workflow.ipynb generated/nested_credit --package-name nested_credit --regression-contract examples/nested_financial/credit_pipeline/regression.json
uv run notebook-to-kedro generate examples/nested_financial/lapse_calibrated_vote/workflow.ipynb generated/nested_lapse --package-name nested_lapse --regression-contract examples/nested_financial/lapse_calibrated_vote/regression.json
uv run pytest tests/unit/test_nested_financial_corpus.py tests/integration/test_nested_financial_models.py --no-cov
uv run python tools/build_nested_financial_examples.py generated/rebuilt_nested_cases
```

Install a generated project's test extra, then run `python -m pytest` and `kedro run` from its
root. Each ships ten regressions: cohort/feature expectations, one hand-computed metric node
example and four exact source-error cases at both pipeline and node level. Model probabilities
and the fitted object have no golden oracle; `regression-coverage.json` retains those gaps.
Generation and the example builder perform no model fitting or notebook execution. The builder
checks the baseline portfolio identity and uses the shared writer without overwriting targets.

## Runtime boundaries retained

Both boundary notebooks have complete static source accounting and can generate a project.
They are runtime evidence, not statically refused layouts:

- [Fitted external alias](credit_pipeline/boundary_fitted_alias.ipynb): the source reads feature
  names through the external `preprocessor` alias after Pipeline fitting. The source succeeds;
  default Kedro MemoryDataset copies leave that separate prototype unfitted, raising
  `NotFittedError`. The working source instead reads the fitted component owned by the returned
  model. This is an unresolved conversion alias-fidelity gap. No copy policy is weakened.
- [Temporal stacking](lapse_calibrated_vote/boundary_stacking_timeseries.ipynb): both source and
  Kedro raise `ValueError: cross_val_predict only works for partitions`. Stacking's
  [cross_val_predict](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.cross_val_predict.html)
  needs every sample in exactly one test partition; the expanding temporal split does not
  satisfy that condition. The converter does not replace it with shuffled/non-temporal folds.

See the [measured report](../../docs/evaluation/nested-financial-models.md) and
[runtime snapshot](observations.json) for preserved outcomes. These examples establish selected
composition evidence, not arbitrary alias handling, scientific quality, production risk models,
survival analysis, regulatory acceptance or measured human savings.
