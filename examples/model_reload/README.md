# Explicit saved-model prediction checks

This separate four-row example demonstrates notebook regression schema 1.1. It does not change
the financial corpus or its expectations. The three procedural cells prepare data, fit a seeded
decision tree and return predictions plus an explicitly selected fitted_model leaf.

The labels split at x=1.5. Probes at the training endpoints 0 and 3 have hand-declared labels
[0, 1] and probabilities [[1, 0], [0, 1]]. The builder writes these declarations without fitting
a model. These in-sample probes test conversion/storage behavior, not scientific quality.

From the repository root, generate into a new directory:

```bash
uv run notebook-to-kedro project generate examples/model_reload/project.json generated/model_reload
cd generated/model_reload
python -m pip install -e '.[test]'
python -m pytest
```

Four delivered tests cover the positive pipeline, header-only source assertion and two actual
save/fresh-process reload checks (predict and predict_proba). Saved versions live only under
each pytest temporary directory. Ordinary regression tests keep their memory-only behavior.
The generated testing guide/report retain missing full-model expectations and not_run statuses;
running pytest supplies separate execution evidence.

Reproduce the six committed machine-readable assets into a new destination:

```bash
uv run python tools/build_model_reload_example.py generated/model_reload_assets
```

See the [contract](../../docs/reference/generated-notebook-tests.md#explicit-persisted-model-prediction-checks)
for budgets, supported descriptors and limitations. These cases are not part of the existing
six-variant fresh-install bootstrap matrix.
