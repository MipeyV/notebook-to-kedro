# Insurance: synthetic 12-month policy lapse

Entirely synthetic: 5,040 rows, one observation per fictional entity, monthly cohorts from January 2018 to December 2024. No personal or real customer data is used.

Target: `lapse_12m`. A simulated policy cessation through nonpayment or policyholder cancellation within 12 months; death, maturity and other competing events are not modeled. This is binary prediction, not survival analysis. There are 514 positive rows. Rates and relationships are invented and uncalibrated.

`data/portfolio.csv` is the main dataset; `dictionary.json` describes units and predictor roles. `manifest.json` pins its hash, seed, counts and feature allowlist. Identifiers, future event/end dates and labels are excluded from predictors.

The ten-cell procedural `workflow.ipynb` filters complete outcome windows, splits cohorts, fits training-only imputation/encoding, trains a seeded forest, chooses a threshold on validation and scores the untouched test cohort. Training uses 2018-2020, validation 2022 and test 2024; 2021/2023 are embargo cohorts. Unknown test categories map to zero in the corresponding training dummy columns.

A missed event costs 4 illustrative units and a false alert one unit. These are declared demonstration assumptions, not estimated financial losses.

`regression.json` supplies known cohort/feature expectations, a hand-calculated four-observation metric oracle and explicit empty/duplicate/incomplete/invalid-label failure cases. Ten shipped tests are expected. Model scores are not captured as golden expectations; model/node coverage gaps remain visible.

`boundary_assertions.ipynb` keeps identical Python instructions with an assertion-only first business cell and must be refused with SA002. `boundary_catalog_reuse.ipynb` reads the raw catalog again for its final row count and must be refused with SA008. The working layout materializes that scalar once. No engine guard is relaxed.

See the [corpus guide](../README.md) for commands, methodology and limitations.
