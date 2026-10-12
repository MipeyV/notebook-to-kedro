# Synthetic pilot review

[Documentation index](../README.md)

Status: **pending independent human review**. This worksheet is assistant-authored preparation,
not approval. All boxes are intentionally unchecked. A merged PR, a passing test, or agreement
between two LLM roles is not evidence that a human has checked the contract.

## Review inputs

Review the [original notebook](../../tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb),
[orders](../../tests/fixtures/notebooks/pilots/customer_churn_v1/orders.csv),
[draft contract](../../tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json),
[expected catalog](../../tests/fixtures/evaluation/pilots/customer_churn_v1/expected_catalog.yml)
and [pilot tests](../../tests/integration/test_synthetic_notebook_pilot.py).
Use the [pilot report](synthetic-notebook-pilot.md) for scope, hashes and reproduction commands.
Inspect source and manually specified expectations before consulting generated outputs.

The reviewer must be a human who did not author the fixture and its expected answers.
Identify the reviewed commit and notebook/CSV SHA-256 values. If source, expectations or
runtime requirements change during review, record the change and review the new revision.
Prior results must not be relabeled as measurements of the changed case.

## Source and catalog checks

- [ ] Confirm the 22 cells are synthetic, outputless and contain no credentials or remote I/O.
- [ ] Confirm `customers` is simulated inside a node using seed `7`, not loaded from a file.
- [ ] Confirm `orders` alone is catalog-backed: pandas `CSVDataset`, copied local CSV at
  `data/01_raw/orders.csv`, 21 rows and the six original columns.
- [ ] Confirm missing units and discount have distinct meanings; no loader coercion or
  global missing-value replacement is silently added.
- [ ] Confirm the single extracted fill-values parameter preserves its original mapping.
  The simulation seed and tree arguments remain literal source under current extraction rules.
- [ ] Confirm pandas `2.3.3` and the locked test dependencies describe the tested runtime;
  no claim is made about pandas 3, Spark, Kaggle or cloud dataset equivalence.

## Hand calculation checks

These calculations are review aids, not an independent oracle. Check them against the CSV
and source, and verify every expected table's rows, indices, columns, missingness and dtypes.

| Rule | Calculation or identity to verify |
| --- | --- |
| Duplicate selection | Keep the first `O02`: `1 * 50 * (1 - 0.2) = 40`, not the later price `999`. |
| Missing discount | `O04` revenue is `1 * 80 * (1 - 0) = 80`; its original discount stays missing. |
| Cancellation and missing units | Remove `O08`, `O17`, `O20` and the later duplicate: `21 - 4 = 17` rows. |
| Refund | Keep `O11`: `-1 * 20 = -20`; C07 totals `120 - 20 = 100` across two orders. |
| Orphan | C99 contributes `999` in aggregates, but is absent from customer-left-joined features. |
| Zero-order clients | C05 and C11 remain, with revenue `0.0`, integer count `0` and average `0.0`. |
| Totals | Aggregates: 11 customers, 17 orders, revenue `2,459`; joined clients: 12 rows, 16 orders, revenue `1,460`. |
| Average order | C01: `100 / 2 = 50`; zero counts use divisor `1`, not division by zero. |

- [ ] Verify the seeded ticket vector, under the locked NumPy runtime, is
  `[4, 3, 3, 4, 2, 3, 4, 1, 0, 1, 1, 4]`; these values are observed but not model features.
- [ ] Verify all six hand-specified tables and the derived feature matrices, not just totals.
- [ ] Verify exact count/target/prediction dtypes and numeric tolerance `rtol=0`, `atol=1e-12`.

## Structure and learning checks

- [ ] Match all nine task boundaries and cell IDs to source. Account for all 35 top-level
  statements exactly once: 30 task statements, four shared imports, one catalog load.
- [ ] Check each ordered input/output and parameter binding, including `X, holdout, y` for
  the split node. Independent simulation/cleaning branches need not run in source-cell order.
- [ ] Confirm all original assertions are preserved, including customer/order uniqueness
  and the intentionally synthetic final `accuracy == 1.0` assertion.
- [ ] Confirm feature order: recency, revenue, completed orders, average order; neither
  target, customer identity, segment nor service tickets is included in `X`.
- [ ] Check holdout IDs C04, C06, C08, C12 correspond to indices `[3, 5, 7, 11]`.
  Train indices are `[0, 1, 2, 4, 6, 8, 9, 10]`; feature and target indices stay aligned.
- [ ] Confirm `DecisionTreeClassifier(max_depth=2, random_state=7)` fits only eight training rows.
- [ ] Confirm ordered predictions `[0, 0, 1, 1]`, confusion `[[2, 0], [0, 2]]` and accuracy `1.0`.
  Both segment summaries have support `2` and accuracy `1.0`.
- [ ] Confirm this deliberately easy classification is a conversion check, not a business
  ML-quality estimate, cross-validation result or evidence of generalization.

## Oracle sensitivity and execution

- [ ] Inspect and run all six trusted negative controls: wrong seed, wrong duplicate,
  omitted refund, inner join, float count and reversed holdout features.
- [ ] Confirm the first five are rejected by observable table/schema differences despite
  unchanged aggregate accuracy. Confirm the sixth fails inside `evaluate_model`.
- [ ] Confirm notebook execution uses a real kernel and an in-memory observer cell without
  editing the original fixture or deriving expected tables from generated output.
- [ ] Confirm generated execution loads the actual catalog CSV, not a substituted memory frame.
- [ ] Confirm this does not establish fresh-install/`kedro run` bootstrap, other datasets,
  other inputs or an OS security sandbox for future untrusted model proposals.

## Decision record

Copy the following structure into a subsequent reviewed change, with real evidence. Do not
fill it with assistant identity, an automated test result or a model's assessment.

```text
Reviewer identity: <human name or handle>
Review date: <YYYY-MM-DD>
Reviewed commit: <full Git commit>
Notebook SHA-256: <reviewed bytes>
CSV SHA-256: <reviewed bytes>
Contract and expected catalog: <reviewed paths at that commit>
Checks completed: <worksheet sections and any exceptions>
Commands and results: <actual runtime and test evidence>
Corrections and rationale: <none, or explicit changes>
Decision: <approved / changes requested>
Evidence reference: <review comment, PR or committed review record>
```

The [human-review evidence API](notebook-human-review.md) now prepares a pending request bound to
the complete reference, source files and typed expectations. Record the actual human decision and
local proof in a separate reviewed change. An operator must externally verify the declaration and
explicitly accept it before producing a separate reviewed-contract wrapper. Keep the original draft
contract/reference pending and unchanged; preserve assistant authorship and exposure history.
Do not replace pending-only assertions with synthetic approval. Any schema extension or legacy
corpus promotion needs explicit validation; do not rename `pilot-draft-1` to a gold schema.
Until then, this remains a development fixture and the live experiment gate stays closed.
The [experiment proposal](whole-notebook-experiment.md) can be prepared and tested offline.
