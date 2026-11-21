# Explicit notebook model output

[Documentation index](../README.md)

Status: initial opt-in notebook leaf persistence, added on 2026-11-21. The declaration selects
one final source symbol; it does not infer an estimator type or change its training code.
Omitting it preserves the existing generated files and memory-only output behavior.

## Declare a model

```bash
uv run notebook-to-kedro generate examples/nested_financial/credit_pipeline/workflow.ipynb \
  generated/stored_credit --package-name stored_credit --model-output fitted_model \
  --regression-contract examples/nested_financial/credit_pipeline/regression.json
```

For a static preview and the existing VS Code configuration selection:

```bash
uv run notebook-to-kedro project plan examples/nested_financial/credit_pipeline/project-model.json
uv run notebook-to-kedro project generate examples/nested_financial/credit_pipeline/project-model.json generated/stored_credit
```

Notebook settings schema 1.0 optionally accepts `"model_output": "fitted_model"`. This is a
source identifier, not a filename, hook or serializer expression. Functional settings reject it.
The [lapse settings](../../examples/nested_financial/lapse_calibrated_vote/project-model.json)
exercise the same option for the calibrated voting model. Original `project.json` settings
remain unchanged. The example builder reproduces both opt-in settings files.

For the Python API, pass `model_output="fitted_model"` and the original `source_facts` to
`generate_kedro_project`. The shared renderer and local operations enforce the same binding.
Source accounting, including SA009, remains mandatory. Low-level generation without source
facts cannot enable this option.

## Binding and artifacts

The symbol must be a Python identifier whose latest generated value is a pipeline leaf.
Unknown, consumed/intermediate, ordering-only-consumed and reserved `parameters` datasets are
refused before publication. Earlier unused versions cannot satisfy a declaration for a later
consumed value. Naming profiles and rebound symbols bind to the renderer's actual dataset name.
This restriction keeps serialization out of intermediate computation and identity semantics.

The catalog adds exactly one entry:

```yaml
fitted_model:
  type: kedro_datasets.pickle.PickleDataset
  filepath: data/06_models/model.pkl
  backend: pickle
  versioned: true
```

`model-output.json` binds the source SHA, symbol, task and dataset to this declaration;
`MODEL_OUTPUT.md` explains its runtime scope. Their execution/reload statuses are `not_run`.
Generation only writes text and ordinary input copies through the shared writer. It does not
fit, serialize, load or type-check an estimator, and creates no model artifact directory.
No sklearn/Kedro/serializer dependency is added to the analysis engine. The generated project
already requires kedro-datasets; the stdlib pickle backend needs no compression/backend extras.

## Execute and reload

Install the generated project and run `kedro run` from its root. A normal new Kedro run creates
a save version at `data/06_models/model.pkl/<version>/model.pkl`. Catalog paths follow the
runtime working directory. Use a fresh catalog for a new run; ordinary Kedro version behavior
does not provide a concurrent writer lock, atomic transaction or partial-file cleanup.

```python
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog

settings = OmegaConfigLoader(conf_source="conf/base")["catalog"]
catalog = DataCatalog.from_config(settings, load_versions={"fitted_model": "YOUR_SAVE_VERSION"})
model = catalog.load("fitted_model")
```

Only load self-produced trusted pickles: [unpickling can execute code](https://docs.python.org/3/library/pickle.html).
Keep compatible Python/library versions and importable model classes available. This is local
Python persistence, not a portable export, deployment package, model registry or arbitrary-object
serialization guarantee. Serialization failures remain dataset/runtime errors.
Only the selected leaf is saved. Other outputs, including a validation-selected threshold or
decision policy, are not bundled automatically; the reload checks compare estimator scores.

## Verification scope

Repository checks on the selected locked runtime compare stored/reloaded credit and calibrated
lapse model predictions and fitted components with original notebook execution under both naming
profiles and SequentialRunner/ThreadRunner. Separate CLI runs create successive versions without
changing earlier files; a fresh Python process reloads both versions and compares test scores.
A fresh-catalog save-version collision must refuse to replace the original bytes.

The ten supplied regressions per example remain memory-only. They verify the exact declared
model catalog entry, remove only that entry for their isolated run and retain all missing model
oracles. A deliberately changed storage backend must fail those tests before a model is saved.
They do not establish persistence, scientific quality or business value. An additional explicit
[notebook regression schema 1.1](generated-notebook-tests.md#explicit-persisted-model-prediction-checks)
now generates real storage/fresh-process prediction checks from supplied probes and oracles.
The original financial contracts and their missing model-object oracles remain unchanged.
The new cases are not added to the existing six-variant fresh-install bootstrap matrix.
See [ADR 0026](../decisions/0026-explicit-notebook-model-output.md).

The separate [financial journey](../evaluation/nested-financial-models.md#measured-installation-journeys)
now generates prediction reload tests for both nested models under default/custom profiles and
checks new installed wheels without source-tree fallback. It explicitly captures references from
the original notebook on eight fixed validation positions, constrains seven known runtime package
versions, and retains hashes, negative controls and machine timings. This does not supply a full
model-state oracle or measured human savings. It runs in its own Python 3.12 CI job; the original
six-variant bootstrap and historical financial observations remain unchanged.
