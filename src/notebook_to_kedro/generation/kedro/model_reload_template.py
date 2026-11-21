"""Standalone model reload tests and a fresh-process worker; no analysis-time execution."""

MODEL_TESTS = """

@pytest.mark.parametrize("check", DATA["contract"]["model_checks"], ids=lambda check: check["id"])
def test_model_reload(check, tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    scenario = next(case for case in CASES if case["id"] == check["scenario"])
    version = "model-check"
    catalog = _catalog(scenario, tmp_path, monkeypatch, save_version=version)
    storage = DATA["model_output"]
    settings = copy.deepcopy(storage["configuration"])
    settings["filepath"] = (tmp_path / settings["filepath"]).as_posix()
    persisted = DataCatalog.from_config({storage["dataset"]: settings}, save_version=version)
    catalog[storage["dataset"]] = persisted[storage["dataset"]]
    pipeline = importlib.import_module(
        DATA["package_name"] + ".pipeline_registry"
    ).register_pipelines()["__default__"]
    SequentialRunner().run(pipeline, catalog)
    for name, expected in scenario["expected"].items():
        _observe(catalog.load(name), expected)
    base = Path(settings["filepath"])
    artifact = base / version / base.name
    assert artifact.is_file(), "The pipeline did not save its declared model artifact"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload = tmp_path / "model-check.json"
    payload.write_text(
        json.dumps(
            {
                "dataset": storage["dataset"],
                "configuration": settings,
                "version": version,
                "artifact": str(artifact),
                "sha256": digest,
                "check": check,
            },
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/_model_reload_worker.py"), str(payload)],
        cwd=tmp_path,
        env=dict(
            os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, "Fresh model reload failed:\\n" + result.stdout + result.stderr
    assert "Model reload predictions matched supplied oracle" in result.stdout
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
"""

MODEL_WORKER = '''"""Reload only the model produced by this test and evaluate its declared probe."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from kedro.io import DataCatalog
import test_notebook_regressions as checks

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
artifact = Path(payload["artifact"])
assert hashlib.sha256(artifact.read_bytes()).hexdigest() == payload["sha256"]
check = payload["check"]
if check["method"] not in ("predict", "predict_proba"):
    raise ValueError("Unsupported model reload method")
catalog = DataCatalog.from_config(
    {payload["dataset"]: payload["configuration"]},
    load_versions={payload["dataset"]: payload["version"]},
)
model = catalog.load(payload["dataset"])
actual = getattr(model, check["method"])(checks._materialize(check["input"]))
expected = checks._materialize(check["expected"])
assert isinstance(actual, np.ndarray)
assert actual.shape == expected.shape
assert actual.dtype == expected.dtype
assert np.isfinite(actual).all()
np.testing.assert_allclose(actual, expected, atol=check["abs_tol"], rtol=check["rel_tol"])
assert hashlib.sha256(artifact.read_bytes()).hexdigest() == payload["sha256"]
print("Model reload predictions matched supplied oracle")
'''
