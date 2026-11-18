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

_FIXTURE_CASES = '''def _fixture_cases():
    """Read only pinned, contained regular scenario files before application imports."""
    contract = DATA["contract"]
    definitions = contract["scenarios"]
    if contract["schema_version"] != "1.1" or not 1 <= len(definitions) <= 100:
        raise ValueError("Invalid generated fixture contract")
    cases, total = [], 0
    for definition in definitions:
        digest = definition["sha256"]
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None or definition["path"] != (
            "regression_fixtures/" + digest + ".json"
        ):
            raise ValueError("Regression fixtures require contained generated paths")
        path = ROOT / "tests" / definition["path"]
        for directory in (ROOT / "tests", path.parent):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Regression fixture directories must be regular")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Regression fixtures must be regular files")
        with path.open("rb") as stream:
            content = stream.read(min(1024 * 1024, 8 * 1024 * 1024 - total) + 1)
        total += len(content)
        if len(content) > 1024 * 1024 or total > 8 * 1024 * 1024:
            raise ValueError("Regression fixture byte budget exceeded")
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Regression fixture SHA-256 mismatch")
        cases.append(json.loads(content.decode("utf-8")))
    return cases


CASES = _fixture_cases()'''

_EXCEPTION_HELPERS = '''_EXCEPTION_TYPES = {
    "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "RuntimeError": RuntimeError,
    "ZeroDivisionError": ZeroDivisionError, "AssertionError": AssertionError,
}


def _assert_exception(error, expectation):
    """Match the concrete built-in type and literal message, without regex or imports."""
    assert type(error) is _EXCEPTION_TYPES[expectation["type"]]
    assert str(error) == expectation["message"]


def _check_pipeline(pipeline, catalog, scenario, monkeypatch):
    if "raises" not in scenario:
        SequentialRunner().run(pipeline, catalog)
        _assert_json(catalog.load(DATA["output_name"]), scenario["expected"])
        return
    expectation = scenario["raises"]
    name = DATA["node_names"][expectation["node"]]
    target = next(node for node in pipeline.nodes if node.name == name)
    original, observed = target.func, []

    @functools.wraps(original)
    def tracked(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except Exception as error:
            observed.append(error)
            raise

    monkeypatch.setattr(target, "func", tracked)
    with pytest.raises(_EXCEPTION_TYPES[expectation["type"]]) as caught:
        SequentialRunner().run(pipeline, catalog)
    _assert_exception(caught.value, expectation)
    assert len(observed) == 1 and observed[0] is caught.value
    assert not catalog.exists(DATA["output_name"])


def _check_node(function, case):
    inputs = copy.deepcopy(case["inputs"])
    if "raises" not in case:
        _assert_json(function(**inputs), case["expected"])
        return
    with pytest.raises(_EXCEPTION_TYPES[case["raises"]["type"]]) as caught:
        function(**inputs)
    _assert_exception(caught.value, case["raises"])
'''


def _with_exception_tests(module: str) -> str:
    return (
        module.replace("import copy\n", "import copy\nimport functools\n")
        .replace(
            "def _assert_json(actual, expected):",
            _EXCEPTION_HELPERS + "\n\ndef _assert_json(actual, expected):",
        )
        .replace(
            "    SequentialRunner().run(pipeline, catalog)\n"
            '    _assert_json(catalog.load(DATA["output_name"]), scenario["expected"])',
            "    _check_pipeline(pipeline, catalog, scenario, monkeypatch)",
        )
        .replace(
            '        result = getattr(nodes, DATA["node_names"][name])'
            '(**copy.deepcopy(case["inputs"]))\n'
            '        _assert_json(result, case["expected"])',
            '        _check_node(getattr(nodes, DATA["node_names"][name]), case)',
        )
    )


def _fixture_data(
    contract: WorkflowRegressionContract, files: dict[Path, str], report: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    references, fixtures = [], []
    for definition, source in zip(
        contract.to_dict()["scenarios"], contract.fixture_jsons, strict=True
    ):
        relative = "regression_fixtures/" + definition["sha256"] + ".json"
        files[Path("tests") / relative] = source
        references.append({"path": relative, "sha256": definition["sha256"]})
        fixtures.append(
            {
                "source": definition["path"],
                "path": "tests/" + relative,
                "sha256": definition["sha256"],
                "size_bytes": len(source.encode("utf-8")),
            }
        )
    data: dict[str, Any] = {"schema_version": "1.1", "scenarios": references}
    module = _FIXTURE_CASES
    if contract.to_dict()["schema_version"] == "1.2":
        data.update(schema_version="1.2", storage="fixtures")
        module = module.replace(
            'contract["schema_version"] != "1.1"',
            '(contract["schema_version"] != "1.2" or contract.get("storage") != "fixtures")',
        )
    report["fixtures"] = fixtures
    return data, module


def render_workflow_regression_tests(
    plan: FunctionalWorkflowPlan,
    profile: KedroArchitectureProfile,
    package_name: str,
    contract: WorkflowRegressionContract | None,
) -> dict[Path, str]:
    """Validate expectations and render tests/gaps without application imports or execution."""
    data: dict[str, Any] = (
        {"schema_version": "1.0", "scenarios": []} if contract is None else contract.resolved_dict()
    )
    if contract is not None:
        validate_regression_binding(contract, plan)
    cases = data["scenarios"]
    counts = {
        step.name: sum(step.name in case.get("nodes", {}) for case in cases) for step in plan.steps
    }
    gaps = [name for name, count in counts.items() if count == 0]
    report: dict[str, Any] = {
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
    if plan.configuration.file_inputs:
        report["missing_file_fixtures"] = [name for name, _ in plan.configuration.file_inputs]
    if plan.configuration.memory_output:
        report["missing_memory_result_expectations"] = True
    if plan.configuration.artifact_destinations:
        report["missing_artifact_expectations"] = [
            name for name, _ in plan.configuration.artifact_destinations
        ]
    files = {Path("regression-coverage.json"): json.dumps(report, sort_keys=True, indent=2) + "\n"}
    if contract is None:
        files[Path("TESTING.md")] = (
            "# Regression tests\n\nNo expectations were supplied; no tests were generated.\n"
            "See regression-coverage.json for missing expectations. Supply an explicit regression "
            "contract when generating a new project.\n"
        )
        if plan.configuration.file_inputs:
            files[Path("TESTING.md")] += (
                "\nFile-reference fixtures are not supported by the JSON regression contract. "
                "Supply reviewed application-level fixture tests separately; "
                "no tests were invented.\n"
            )
        if plan.configuration.memory_output:
            files[Path("TESTING.md")] += (
                "\nMemory-only results require explicit application-level expectations. "
                "The JSON regression contract does not define typed result comparisons.\n"
            )
        if plan.configuration.artifact_destinations:
            files[Path("TESTING.md")] += (
                "\nRuntime artifacts require reviewed application-level expectations; "
                "the JSON regression contract does not define artifact fixtures.\n"
            )
        return files
    declaration = contract.to_dict()
    module = _TEST_MODULE
    exceptions = declaration["schema_version"] == "1.2"
    if exceptions:
        report["pipeline_exception_scenarios"] = sum("raises" in case for case in cases)
        report["node_exception_scenarios"] = {
            step.name: sum("raises" in case.get("nodes", {}).get(step.name, {}) for case in cases)
            for step in plan.steps
        }
        files[Path("regression-coverage.json")] = (
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )
        module = _with_exception_tests(module)
    if contract.fixture_jsons:
        data, fixture_module = _fixture_data(contract, files, report)
        files[Path("regression-coverage.json")] = (
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )
        module = module.replace(
            "import copy\n", "import copy\nimport hashlib\nimport stat\n"
        ).replace('CASES = DATA["contract"]["scenarios"]', fixture_module)
    metadata = {
        "schema_version": "1.0",
        "contract_sha256": contract.sha256,
        "package_name": package_name,
        "nodes_module": f"{package_name}.pipelines.{profile.pipeline_name}.nodes",
        "node_names": {step.name: profile.node_name_prefix + step.name for step in plan.steps},
        "output_name": plan.configuration.outputs[0][0],
        "contract": data,
    }
    compile(module, "tests/test_workflow_regressions.py", "exec", dont_inherit=True)
    files[Path("tests/test_workflow_regressions.py")] = module
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
    if contract.fixture_jsons:
        files[Path("TESTING.md")] += (
            "\nScenario fixtures are copied under tests/regression_fixtures with pinned SHA-256 "
            "identities. They are validated before collection; missing, modified or linked files "
            "fail before node execution. Original source paths are listed in "
            "regression-coverage.json.\n"
        )
    if exceptions:
        files[Path("TESTING.md")] += (
            "\nException expectations match a declared concrete built-in type and literal message. "
            "Pipeline tests additionally require the exception from the declared node function "
            "and no final report in the fresh temporary workspace. Fixture/catalog setup and "
            "registry construction occur outside the expected-exception context.\n"
        )
    return files
