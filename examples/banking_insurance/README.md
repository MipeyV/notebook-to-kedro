# Synthetic banking and insurance business cases

Invented datasets and procedural ML workflows for exercising Notebook to Kedro. There are no
real clients, policies, loans or externally sourced personal records. Event rates, relationships
and costs are simulation assumptions, not empirical estimates or decision rules.
The counts below describe the committed seed-42 corpus; another seed creates a separate realization.

| Case | Main rows | Positive events | Numeric/categorical predictors | Target |
| --- | --- | --- | --- | --- |
| [Credit default](credit_default/README.md) | 4,200 | 394 (9.38%) | 9 / 3 | `default_12m` |
| [Policy lapse](insurance_lapse/README.md) | 5,040 | 514 (10.20%) | 9 / 3 | `lapse_12m` |

Each case contains `data/portfolio.csv`, four small failure fixtures, a data dictionary,
SHA-pinned manifest, ten-cell notebook, local settings and explicit regression contract.
The main CSVs stay below the existing 1 MiB regression-fixture budget.

## Data and modeling design

There is one snapshot per fictional entity, with monthly cohorts from January 2018 through
December 2024. All main rows have 12 months of follow-up, ending before the January 2026 cutoff.
Event months are simulated within that horizon. There is no payment ledger, mortality model,
competing-risk model or real macroeconomic series.

Features include missing values, dependence between income/debt or premium changes, imbalanced
outcomes and time-related shifts. A new channel category appears only in the test cohort.
Missingness is about 4% per feature. The hidden event probability is never written as a predictor.
`dictionary.json` gives feature meanings and units. Currency and coverage units are arbitrary.

| Cohort | Observation years | Credit rows | Lapse rows |
| --- | --- | --- | --- |
| Training | 2018-2020 | 1,800 | 2,160 |
| Embargo | 2021 | 600 | 720 |
| Validation | 2022 | 600 | 720 |
| Embargo | 2023 | 600 | 720 |
| Test | 2024 | 600 | 720 |

The embargo years prevent training outcome windows from overlapping validation observation
times, and validation outcome windows from overlapping test observation times. Identifiers,
follow-up metadata, future event dates and targets are excluded through an explicit feature
allowlist. Imputation and dummy-column selection use training only. Validation chooses among
five thresholds using declared missed-event/false-alert costs (credit 12:1; lapse 4:1). These
are demonstration weights, not estimated financial losses. The test cohort is scored after
that choice; forest scores are not calibrated business PDs.

The notebooks report ROC AUC, average precision, Brier score, precision, recall, confusion
counts, alert rate and illustrative cost. `scored_test` retains IDs, observation months, labels,
scores and predictions for evaluation. Outputs remain in memory; no model/result serializer is
added. The lapse target covers simulated nonpayment/cancellation cessation only, rather than
every contractual discontinuity option or actuarial survival analysis.

## Generate a Kedro project

Run from the repository root:

```bash
uv run notebook-to-kedro project plan examples/banking_insurance/credit_default/project.json
uv run notebook-to-kedro generate examples/banking_insurance/credit_default/workflow.ipynb generated/credit_case --package-name credit_case --regression-contract examples/banking_insurance/credit_default/regression.json
uv run notebook-to-kedro generate examples/banking_insurance/insurance_lapse/workflow.ipynb generated/lapse_case --package-name lapse_case --regression-contract examples/banking_insurance/insurance_lapse/regression.json
```

Install the generated project with its test extra, then run `python -m pytest` and `kedro run`
from its root. Generation does not execute the notebook or infer its oracles. The local settings
can also be selected by the VS Code operations.

The two recognized forest parameters become Kedro parameters. Cohort cutoffs, preprocessing,
threshold grid and illustrative costs remain explicit source logic; they are not automatically
promoted to a universal business configuration.

## Verification and gaps

Each project ships ten tests: five pipeline cases and five node cases. Explicit oracles cover
cohort counts, training feature names, a hand-calculated four-observation metric example, and
source failures for empty data, duplicate IDs, incomplete follow-up and invalid targets.
The metric example has AUC 0.75, average precision 5/6, Brier score 0.158125 and confusion matrix
`[[2, 0], [1, 1]]`, independently of the trained model and synthetic portfolio outcomes.

Full portfolio model scores are absent from golden regression expectations; the generated gap
report retains missing expectations. Separate repository tests compare original notebook
execution with all generated leaf outputs under both runners/profiles, recompute metrics and
thresholds independently, perturb holdout labels/values to check fitting isolation, and invert
generated test scores as a negative control:

```bash
uv run pytest tests/integration/test_financial_business_cases.py --no-cov
```

Two layouts per case are intentionally blocked: `boundary_assertions.ipynb` has identical Python
instructions but an assertion-only mixed cell (SA002); `boundary_catalog_reuse.ipynb` reuses the
raw catalog for a later row count (SA008). The working layout groups initial guards with
preparation and materializes that scalar once. These failures remain evidence of the current
scope; no analyzer or source-accounting rule is relaxed.

## Reproduce the artifacts

```bash
uv run python tools/build_financial_examples.py generated/rebuilt_financial_cases --seed 42
```

The output directory must be new. A SHA-256 counter keyed by seed, case, row and field supplies
integer simulation draws. Generation uses integer event-probability basis points and no model
execution. The shared writer publishes contained files without overwriting an existing target.
Seeds change invented records; they do not calibrate the simulation to a population.

## Methodological references

- [scikit-learn: common pitfalls and data leakage](https://scikit-learn.org/stable/common_pitfalls):
  learn preprocessing from training data and keep test data out of model choices.
- [EIOPA: discontinuity-option definitions](https://www.eiopa.europa.eu/rulebook/solvency-ii-single-rulebook/article-2414_en):
  background on the broader contractual context; the target above is deliberately narrower.

These cases establish controlled conversion evidence. Real portfolio representativeness,
fairness, calibration, economic value, regulatory compliance and human productivity gains
are not established by synthetic metrics.
