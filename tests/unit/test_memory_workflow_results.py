"""Memory-only final output is an explicit opt-in boundary, not a serializer fallback."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
    plan_functional_workflow_path,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalWorkflowError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_files"
SOURCE = EXAMPLE / "src/reference_ml/memory_workflow.py"


def _config() -> FunctionalWorkflowConfiguration:
    return load_functional_workflow_configuration(EXAMPLE / "memory_workflow.json")


def test_memory_mode_keeps_an_explicit_named_output_and_fresh_serialization() -> None:
    config = _config()
    assert config.memory_output
    assert config.outputs == (("result", "memory"),)
    data: Any = config.to_dict()
    assert FunctionalWorkflowConfiguration.from_dict(data) == config
    data["outputs"]["result"] = "changed"
    assert config == _config()
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    payload = json.loads(plan.to_json())
    assert payload["schema_version"] == "1.4"
    assert payload["result_boundary"] == {
        "dataset": "result",
        "mode": "memory",
        "persistence": "none",
        "type_validation": "not_performed",
        "artifact_policy": "not_defined",
    }
    assert len(plan.order_after) == 1
    assert len(plan.file_inputs) == 2


@pytest.mark.parametrize("schema", ["1.0", "1.1", "1.2", "1.3", "1.4"])
def test_old_schemas_never_silently_accept_memory_outputs(schema: str) -> None:
    config = _config()
    with pytest.raises(FunctionalWorkflowError, match="one output"):
        replace(
            config,
            schema_version=schema,
            file_inputs=(),
            source_package=config.source_package if schema in {"1.3", "1.4"} else None,
        )


@pytest.mark.parametrize(
    "output",
    [
        None,
        "Memory",
        "memory/result",
        "pickle",
        {"type": "memory"},
        "../result.json",
        "data/08_reporting/result.pkl",
    ],
)
def test_memory_mode_does_not_accept_inferred_serializers_or_paths(output: Any) -> None:
    with pytest.raises(FunctionalWorkflowError, match="one output"):
        replace(_config(), outputs=(("result", output),))


def test_schema_15_retains_explicit_json_output() -> None:
    config = replace(_config(), outputs=(("result", "data/08_reporting/result.json"),))
    assert not config.memory_output
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    payload = json.loads(plan.to_json())
    assert payload["result_boundary"]["mode"] == "json"
    assert payload["result_boundary"]["persistence"] == "json_file"
    files, _ = render_functional_workflow(plan, root=ROOT, package_name="json_case")
    assert json.loads(files[Path("conf/base/catalog.yml")])["result"]["type"] == "json.JSONDataset"


def test_schema_15_still_requires_package_and_explicit_file_input_mapping() -> None:
    data: Any = _config().to_dict()
    data.pop("file_inputs")
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)
    with pytest.raises(FunctionalWorkflowError, match="source_package"):
        replace(_config(), source_package=None)


def test_generation_declares_assign_memory_and_no_result_file_or_fake_tests(tmp_path: Path) -> None:
    output = tmp_path / "project"
    paths = generate_functional_kedro_project(SOURCE, _config(), output, project_root=ROOT)
    catalog = json.loads((output / "conf/base/catalog.yml").read_text())
    assert catalog["result"] == {"type": "MemoryDataset", "copy_mode": "assign"}
    assert not (output / "data/08_reporting").exists()
    assert not (output / "memory").exists()
    gaps = json.loads((output / "regression-coverage.json").read_text())
    assert gaps["missing_memory_result_expectations"] is True
    assert gaps["execution_status"] == "not_run"
    assert "typed result comparisons" in (output / "TESTING.md").read_text()
    assert not any("test_workflow_regressions.py" in str(path) for path in paths)


def test_json_regression_contract_cannot_fabricate_a_memory_result_oracle(tmp_path: Path) -> None:
    # JSON-only inputs avoid masking this check behind the separate file-fixture rejection.
    source = ROOT / "examples/functional_package/src/example_ml/workflow.py"
    config = replace(
        load_functional_workflow_configuration(ROOT / "examples/functional_package/workflow.json"),
        schema_version="1.5",
        outputs=(("total", "memory"),),
    )
    with pytest.raises(WorkflowRegressionError, match="memory-result expectations"):
        generate_functional_kedro_project(
            source,
            config,
            tmp_path / "out",
            project_root=ROOT,
            regression_contract=load_workflow_regression_contract(
                ROOT / "examples/functional_package/regression.json"
            ),
        )
    assert not (tmp_path / "out").exists()


def test_original_source_output_name_and_final_result_guard_remain_enforced() -> None:
    with pytest.raises(FunctionalWorkflowError, match="named return"):
        plan_functional_workflow_path(
            SOURCE, replace(_config(), outputs=(("renamed", "memory"),)), project_root=ROOT
        )


def test_cli_static_plan_and_generation_do_not_serialize_a_business_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [str(SOURCE), str(EXAMPLE / "memory_workflow.json"), "--project-root", str(ROOT)]
    assert main(["plan-workflow", *args]) == 0
    assert json.loads(capsys.readouterr().out)["result_boundary"]["mode"] == "memory"
    output = tmp_path / "out"
    assert main(["generate-workflow", *args, str(output)]) == 0
    assert "Created functional Kedro project" in capsys.readouterr().out
    assert not (output / "data/08_reporting").exists()
