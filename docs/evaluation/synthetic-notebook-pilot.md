# Synthetic whole-notebook pilot

[Documentation index](../README.md)

Status: reproducible deterministic pilot with a **pending independent human review**.
This is an assistant-authored synthetic development case, not an approved gold corpus,
a real customer notebook, a live LLM measurement or a production-readiness claim.

## Files and provenance

- [Notebook](../../tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb):
  22 cells, stable metadata IDs, no committed execution counts or outputs.
- [Orders CSV](../../tests/fixtures/notebooks/pilots/customer_churn_v1/orders.csv):
  21 deliberately constructed synthetic rows, with no customer information or credentials.
- [Draft contract](../../tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json):
  notebook/CSV hashes, source descriptions, intended boundaries, expected values and controls.
- [Expected catalog](../../tests/fixtures/evaluation/pilots/customer_churn_v1/expected_catalog.yml):
  hand-specified YAML independent of generated catalog output.
- [Tests](../../tests/integration/test_synthetic_notebook_pilot.py):
  static contracts, a real Jupyter kernel and generated Kedro execution.

Expected business tables, row identities, splits, predictions and metrics were specified
separately from the V1 renderer. The seeded ticket vector was checked with NumPy; it was not
derived from generated Kedro code. The same assistant authored the source and expectations,
so these are not independently reviewed references. The contract deliberately uses
`pilot-draft-1`, not the approved planning/node/behavioral corpus schemas.
Its exposure field means no calls to local benchmark providers, not that the assistant-authored
fixture was created without LLM assistance.
The historical `v1`, `v2` and `v3` corpora and measured artifacts are unchanged.

## Workflow and sources

The workflow simulates twelve clients using `np.random.default_rng(7)` for service tickets,
then combines them with local orders. Recency, segments and labels are deliberately specified
so classification is simple; the toy accuracy cannot represent a business model's quality.

The CSV contains a conflicting duplicate order, two cancellations, missing units, a missing
discount, a negative-unit refund and an orphan customer ID. The intended cleaning keeps the
first duplicate, excludes cancellations/missing units, fills the missing discount only for
revenue calculation and retains refunds. Seventeen orders remain. Aggregation includes the
orphan, while the customer-left join produces twelve clients, including zero-order clients.

Nine generated nodes cover:

1. Simulate customers.
2. Clean orders.
3. Aggregate revenue and order counts.
4. Join customer features and fill missing aggregates.
5. Prepare features, targets and the explicit holdout mask.
6. Split eight training rows and four held-out rows.
7. Train the decision tree with its original depth and random state.
8. Predict the holdout.
9. Evaluate accuracy, confusion and segment support/accuracy.

All 35 top-level source instructions are accounted for once: 30 belong to the nine tasks,
four are shared imports and one becomes catalog-backed loading. Original notebook metadata
IDs are recorded separately from normalized analyzer IDs such as `cell-0003`.
Nodes must preserve dataset wiring, not the notebook's scheduling order for independent branches.

The current deterministic planner automatically interprets the literal CSV loading expression:

```yaml
orders:
  type: kedro_datasets.pandas.CSVDataset
  filepath: data/01_raw/orders.csv
```

Generated projects copy the CSV to that location. Tests parse the actual generated YAML with
Kedro's config loader, instantiate `DataCatalog.from_config` and load a real `CSVDataset`.
They do not inject a manually loaded pandas frame in place of this external dataset.
Simulation remains a node output in memory, with no invented file path or persistent catalog
entry. Its seed and the tree parameters remain in source; current extraction does not support
those parameter families. The fill-values mapping is the one extracted parameter.
Source descriptions in the draft contract are evaluation expectations, not a new public
automatic source-descriptor API.

Execution uses the generated registry, configuration and a `SequentialRunner` in the locked
test environment. It does not yet test installing a generated project into a fresh environment
or bootstrapping a separate `kedro run` CLI process; those are distinct acceptance gates.

## Observable contract

Compare the notebook and generated pipeline against the separately specified expectations:

- Customers, cleaned orders, aggregates and joined features: columns, indices, row order,
  values, missingness and dtypes.
- Feature matrices and target/mask series: selected columns, split membership, index alignment,
  values and dtypes. Numeric table tolerance is absolute `1e-12`, relative `0`.
- Model class, depth, seed, classes, training sample count and number of features.
- Four ordered predictions `[0, 0, 1, 1]`, integer dtypes and confusion `[[2, 0], [0, 2]]`.
- Accuracy `1.0` and two segments, each with support `2` and accuracy `1.0`.

Tests append an observation cell to an in-memory notebook copy; source files remain outputless.
Generated pipelines use test-only observing memory datasets that copy produced values before
normal runner release. This instrumentation does not rewrite nodes, replace the CSV reader,
or generate expected answers from pipeline results. Comparisons do not establish equivalence
for other inputs, serialization formats or execution environments.

## Negative controls

Six explicit, trusted test-only mutations verify sensitivity:

| Change | Expected detection |
| --- | --- |
| Different simulation seed | Changed customer ticket values. |
| Keep the last duplicate | Wrong cleaned-order identity/order and revenue. |
| Drop refunds | Missing cleaned row and incorrect aggregates. |
| Inner customer join | Missing zero-order clients. |
| Float order-count dtype | Schema mismatch despite equal numeric values. |
| Reverse holdout feature rows only | Wrong predictions trigger the original evaluation assertion. |

The first five still obtain aggregate accuracy `1.0`; their table/schema mismatches prove why
accuracy-only comparison is insufficient. The reversed-holdout test checks that the exception
comes from the generated evaluation node, not a setup assertion. Mutants are constructed only
inside tests. They are not accepted provider proposals, approved references or a relaxed
production validation mode.

## Runtime and reproduction

The minimal published package still depends only on `nbformat`. The test group now includes
`kedro-datasets[pandas-csvdataset]>=8,<9`, matching the generator's existing datasets major
version and installing only the CSV dependency family. The resolved `8.1.0` extra requires
pandas below 3, so the lockfile moves pandas from `3.0.5` to `2.3.3`; other version constraints,
prompts, generators and validators are unchanged. This is a changed development runtime,
not a same-runtime remeasurement of historical model experiments.
Both the source notebook and generated nodes are tested with pandas `2.3.3`; this does not
establish equivalence across pandas major versions or infer the original runtime of a real notebook.

```bash
uv sync --locked --python 3.12
uv run --python 3.12 pytest -o addopts= tests/integration/test_synthetic_notebook_pilot.py
```

To inspect a generated project, choose a new output directory (existing destinations are refused):

```bash
uv run notebook-to-kedro generate \
  tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb \
  generated/customer_churn_pilot_v1 --package-name customer_churn_pilot
```

The original three unmarked checks run in the deterministic matrix. One integration test executes
a real notebook; seven end-to-end cases execute the baseline or controlled generated variants.
The offline batch increment adds five unmarked fixed-response checks and one end-to-end
trusted-body pipeline check, bringing the current pilot module to seventeen cases.
The observation fixture shares one kernel execution within a test session. No Ollama, cloud
endpoint, Kaggle download, Spark session, remote tracker or untrusted model code is contacted.

## Local verification

On 2026-10-11, Windows tests passed with the updated lockfile:

| Suite | Python | Result |
| --- | --- | --- |
| Complete primary suite | 3.12.14 | 1,263 passed; 100% line/branch coverage. |
| Deterministic compatibility suite | 3.11.16 | 1,223 passed, 40 deselected; 100% coverage. |
| Deterministic compatibility suite | 3.13.14 | 1,223 passed, 40 deselected; 100% coverage. |

All eleven pilot cases pass, including the six negative controls. The observed baseline has
twelve feature rows, eight training rows and four ordered held-out predictions, with the
expected confusion matrix and two segment summaries. These are checks of a deliberately easy
synthetic workflow, not an ML accuracy estimate, an independent gold review or a model-provider
comparison. The generated example under `generated/customer_churn_pilot_v1` is local and ignored
by Git; committed fixtures and tests reconstruct it independently.

## Review gate and next step

A [review worksheet](synthetic-pilot-review.md) now lists the source/catalog, manual calculation,
structure and sensitivity checks, with an explicit human decision-record template. All review
boxes remain unchecked. The [whole-notebook experiment proposal](whole-notebook-experiment.md)
defines the later nine-body run, complete-pipeline denominators, evidence and offline gates;
it is not an implemented runner or a live measurement.
The first [offline batch increment](offline-notebook-body-batch.md) now validates recorded bodies
and exercises trusted fixed assemblies through the complete pilot in a temporary test project.
This does not approve the fixture or enable execution of untrusted provider proposals.
The trusted-body pipeline test now uses the [draft source binding](notebook-source-binding.md):
four exact file identities, pending provenance and a rebuilt deterministic plan/request inventory
are checked before assembly. The historical eleven-case verification above remains its original snapshot.

A reviewer must inspect the original cells, source interpretation, duplicate/refund/join rules,
task interfaces, catalog, hand calculations, split alignment and negative controls. Record the
reviewer and evidence in a subsequent reviewed contract change; a green CI or merged PR alone
does not make this case independently approved. The pending-review assertions are intentional
and must be replaced by explicit reviewed evidence when promoting the pilot.

Then implement and verify the proposed offline harness before opting into a live whole-notebook
model experiment, preserving complete rejected denominators and durable raw evidence. Automatic
project injection of LLM proposals remains disabled. Broader simulation/sklearn acquisition descriptors and
Kaggle, Spark/Databricks, AWS/GCP integration require separate scoped increments and real loader
tests. This pilot proves only one controlled simulation-plus-local-CSV workflow.
