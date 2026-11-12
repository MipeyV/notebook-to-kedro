"""Render standalone pytest checks using supplied oracles, never measured application output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.generation.kedro.regression_contract import validate_regression_binding

if TYPE_CHECKING:
    from typing import Any

    from notebook_to_kedro.generation.kedro.profiles import KedroArchitectureProfile
    from notebook_to_kedro.generation.kedro.regression_contract import WorkflowRegressionContract
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan

_TEST_MODULE = '''"""Supplied JSON expectations; running pytest executes project code."""

import copy
import importlib
import json
import re
from pathlib import Path

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "tests/regression_cases.json").read_text(encoding="utf-8"))
CASES = DATA["contract"]["scenarios"]


def _assert_json(actual, expected):
    """Compare JSON representations, distinguishing booleans, integers and floats."""
    options = {"sort_keys": True, "allow_nan": False, "separators": (",", ":")}
    assert json.dumps(actual, **options) == json.dumps(expected, **options)


def _catalog(tmp_path, monkeypatch, scenario):
    loader = OmegaConfigLoader(conf_source=str(ROOT / "conf/base"))
    config = {name: dict(value) for name, value in loader["catalog"].items()}
    # Tests must not write outside their temporary project, even after catalog edits.
    for value in config.values():
        if value["type"] == "MemoryDataset":
            continue
        path = value.get("filepath")
        if value["type"] != "json.JSONDataset" or not isinstance(path, str) or re.fullmatch(
            r"data/(01_raw|08_reporting)/[a-z][a-z0-9_]*\\.json", path
        ) is None:
            raise ValueError("Regression tests require contained generated JSON catalog paths")
    for name, value in scenario["inputs"].items():
        path = tmp_path / config[name]["filepath"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    catalog = DataCatalog.from_config(config)
    for name in loader["parameters"]:
        catalog[f"params:{name}"] = MemoryDataset(copy.deepcopy(scenario["parameters"][name]))
    return catalog


@pytest.mark.parametrize("scenario", CASES, ids=lambda case: case["id"])
def test_pipeline_scenario(scenario, tmp_path, monkeypatch):
    catalog = _catalog(tmp_path, monkeypatch, scenario)
    registry = importlib.import_module(DATA["package_name"] + ".pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    SequentialRunner().run(pipeline, catalog)
    _assert_json(catalog.load(DATA["output_name"]), scenario["expected"])


NODE_CASES = [
    pytest.param(name, case, id=scenario["id"] + "--" + name)
    for scenario in CASES for name, case in scenario.get("nodes", {}).items()
]

if NODE_CASES:
    @pytest.mark.parametrize(("name", "case"), NODE_CASES)
    def test_node_scenario(name, case):
        nodes = importlib.import_module(DATA["nodes_module"])
        result = getattr(nodes, DATA["node_names"][name])(**copy.deepcopy(case["inputs"]))
        _assert_json(result, case["expected"])
'''


def render_workflow_regression_tests(
    plan: FunctionalWorkflowPlan,
    profile: KedroArchitectureProfile,
    package_name: str,
    contract: WorkflowRegressionContract | None,
) -> dict[Path, str]:
    """Validate expectations and render tests/gaps without application imports or execution."""
    data: dict[str, Any] = (
        {"schema_version": "1.0", "scenarios": []} if contract is None else contract.to_dict()
    )
    if contract is not None:
        validate_regression_binding(contract, plan)
    cases = data["scenarios"]
    counts = {
        step.name: sum(step.name in case.get("nodes", {}) for case in cases) for step in plan.steps
    }
    gaps = [name for name, count in counts.items() if count == 0]
    report = {
        "schema_version": "1.0",
        "status": "no_expectations" if contract is None else "expectations_provided",
        "contract_sha256": None if contract is None else contract.sha256,
        "pipeline_scenarios": len(cases),
        "node_scenarios": counts,
        "missing_node_expectations": gaps,
        "missing_pipeline_expectations": not bool(cases),
        "execution_status": "not_run",
        "review_status": "not_authenticated",
    }
    files = {Path("regression-coverage.json"): json.dumps(report, sort_keys=True, indent=2) + "\n"}
    if contract is None:
        files[Path("TESTING.md")] = (
            "# Regression tests\n\nNo expectations were supplied; no tests were generated.\n"
            "See regression-coverage.json for missing expectations. Supply an explicit regression "
            "contract when generating a new project.\n"
        )
        return files
    metadata = {
        "schema_version": "1.0",
        "contract_sha256": contract.sha256,
        "package_name": package_name,
        "nodes_module": f"{package_name}.pipelines.{profile.pipeline_name}.nodes",
        "node_names": {step.name: profile.node_name_prefix + step.name for step in plan.steps},
        "output_name": plan.configuration.outputs[0][0],
        "contract": data,
    }
    compile(_TEST_MODULE, "tests/test_workflow_regressions.py", "exec", dont_inherit=True)
    files[Path("tests/test_workflow_regressions.py")] = _TEST_MODULE
    files[Path("tests/regression_cases.json")] = (
        json.dumps(metadata, sort_keys=True, indent=2) + "\n"
    )
    files[Path("TESTING.md")] = (
        "# Regression tests\n\nReview tests/regression_cases.json before execution.\n\n"
        '```bash\npython -m pip install -e ".[test]"\npython -m pytest\n```\n\n'
        "Running pytest executes project code in this process; this is not a sandbox.\n"
        "Pipeline tests use temporary JSON files and scenario parameters; node tests use only "
        "supplied node expectations. JSON comparisons distinguish booleans/integers/floats.\n"
        "Missing node expectations are listed in regression-coverage.json. Generated tests "
        "are not a proof of business intent, a recorded execution result or authenticated review.\n"
        "Fresh dependency installation is not verified by generation.\n"
    )
    return files
