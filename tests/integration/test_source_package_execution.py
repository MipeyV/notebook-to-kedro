"""Copied and wheel-packaged source modules preserve imports, resources and identities."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner

from notebook_to_kedro import (
    KedroArchitectureProfile,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_package"
PACKAGE = EXAMPLE / "src/example_ml"

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clean_package_modules() -> Iterator[None]:
    prior = {
        name: module
        for name, module in sys.modules.items()
        if name == "example_ml" or name.startswith("example_ml.")
    }
    for name in prior:
        del sys.modules[name]
    yield
    for name in list(sys.modules):
        if name == "example_ml" or name.startswith("example_ml."):
            del sys.modules[name]
    sys.modules.update(prior)


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("case_id", ["positive", "negative"])
def test_generated_package_runs_without_the_original_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_id: str, *, custom_profile: bool
) -> None:
    case = next(
        item
        for item in load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()[
            "scenarios"
        ]
        if item["id"] == case_id
    )
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    package_name = f"packaged_{case_id}_{int(custom_profile)}"
    profile = (
        KedroArchitectureProfile("test.package", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        PACKAGE / "workflow.py",
        config,
        destination,
        project_root=ROOT,
        package_name=package_name,
        architecture_profile=profile,
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    workflow = importlib.import_module("example_ml.workflow")
    assert workflow.__file__ is not None
    assert Path(workflow.__file__).is_relative_to(destination / "src/example_ml")
    assert workflow.prepare.__module__ == "example_ml.workflow"
    registry = importlib.import_module(f"{package_name}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    (destination / "data/01_raw/values.json").write_text(
        json.dumps(case["inputs"]["values"]), encoding="utf-8"
    )
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:scale"] = MemoryDataset(case["parameters"]["scale"])
    original = workflow.summarize
    seen: list[Any] = []

    def summarize(prepared: Any) -> Any:
        seen.append(prepared)
        return original(prepared)

    pipeline_name = "notebook_pipeline" if profile is None else profile.pipeline_name
    nodes = importlib.import_module(f"{package_name}.pipelines.{pipeline_name}.nodes")
    monkeypatch.setattr(nodes, "summarize", summarize)
    SequentialRunner().run(pipeline, catalog)
    assert len(seen) == 1
    assert type(seen[0]).__module__ == "example_ml.domain"
    assert (
        json.loads((destination / "data/08_reporting/total.json").read_text()) == case["expected"]
    )
    assert f"{package_name}.workflow_source" not in sys.modules


_WHEEL_PROBE = """import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import example_ml.workflow as workflow
from example_ml.domain import Intermediate
root = Path(sys.argv[1]).resolve()
assert Path(workflow.__file__).resolve().is_relative_to(root)
assert workflow.prepare.__module__ == "example_ml.workflow"
assert workflow.workflow(3.0, 2.0) == {
    "value": 6.25, "type_module": "example_ml.domain", "helper_module": "example_ml.transforms"
}
registry = importlib.import_module("wheel_case.pipeline_registry")
assert len(registry.register_pipelines()["__default__"].nodes) == 2
print(json.dumps({"module": str(workflow.__file__), "type_module": Intermediate.__module__}))
"""


@pytest.mark.integration
def test_wheel_contains_original_package_resources_and_runs_from_an_unpacked_wheel(
    tmp_path: Path,
) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    project = tmp_path / "project"
    generate_functional_kedro_project(
        PACKAGE / "workflow.py", config, project, project_root=ROOT, package_name="wheel_case"
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    built = subprocess.run(
        [sys.executable, "-I", "-m", "hatchling", "build", "--target", "wheel"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next((project / "dist").glob("*.whl"))
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(wheel) as archive:
        assert archive.read("example_ml/workflow.py") == (PACKAGE / "workflow.py").read_bytes()
        assert (
            archive.read("example_ml/assets/offset.json")
            == (PACKAGE / "assets/offset.json").read_bytes()
        )
        archive.extractall(unpacked)
    # The generated source tree is absent during the runtime probe.
    shutil.move(str(project / "src"), str(tmp_path / "source_not_on_import_path"))
    empty = tmp_path / "empty"
    empty.mkdir()
    result = subprocess.run(
        [sys.executable, "-I", "-c", _WHEEL_PROBE, str(unpacked)],
        cwd=empty,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "example_ml.domain" in result.stdout
