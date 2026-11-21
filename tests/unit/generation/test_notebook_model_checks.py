"""Reload declarations remain finite, explicit, immutable and source-independent."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from notebook_to_kedro import (
    NotebookRegressionContract,
    analyze_notebook_path,
    generate_kedro_project,
    load_notebook_regression_contract,
    plan_notebook_path,
)
from notebook_to_kedro.exceptions import ProjectGenerationError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.generation.kedro.regression_contract import MAX_SCENARIOS
from notebook_to_kedro.generation.writer import write_project

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/model_reload"


def _data() -> Any:
    return json.loads((EXAMPLE / "regression.json").read_text(encoding="utf-8"))


def _contract(data: Any) -> NotebookRegressionContract:
    return NotebookRegressionContract.from_dict(
        data,
        fixture_texts=tuple(
            (name, (EXAMPLE / definition["path"]).read_text(encoding="utf-8"))
            for name, definition in data["fixtures"].items()
        ),
    )


def test_probe_only_fixture_is_pinned_and_contracts_remain_immutable() -> None:
    contract = load_notebook_regression_contract(EXAMPLE / "regression.json")
    assert contract == _contract(_data())
    data = contract.to_dict()
    data["model_checks"][0]["expected"]["data"][0] = 99
    assert contract.to_dict()["model_checks"][0]["expected"]["data"] == [0, 1]
    assert len(contract.fixture_texts) == 3


_MISSING = object()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "1.0"),
        (("model_checks",), _MISSING),
        (("execute",), True),
        (("model_checks",), {}),
        (("model_checks",), [None] * (MAX_SCENARIOS + 1)),
        (("model_checks", 0), None),
        (("model_checks", 0, "abs_tol"), _MISSING),
        (("model_checks", 0, "expression"), "model.predict(X)"),
        (("model_checks", 0, "id"), []),
        (("model_checks", 0, "id"), "../outside"),
        (("model_checks", 1, "id"), "reload-labels"),
        (("model_checks", 0, "scenario"), []),
        (("model_checks", 0, "scenario"), "missing"),
        (("model_checks", 0, "scenario"), "empty"),
        (("model_checks", 0, "method"), "__reduce__"),
        (("model_checks", 0, "abs_tol"), -1),
        (("model_checks", 0, "rel_tol"), -1),
        (("model_checks", 0, "abs_tol"), True),
        (("model_checks", 0, "rel_tol"), "0"),
        (("model_checks", 0, "abs_tol"), float("inf")),
        (("model_checks", 0, "input"), {"kind": "json", "value": [[0], [3]]}),
        (("model_checks", 0, "expected"), {"kind": "json", "value": [0, 1]}),
        (("model_checks", 0, "input", "fixture"), "missing"),
        (("model_checks", 0, "expected", "data"), []),
        (("model_checks", 0, "expected", "data"), [[]]),
        (("model_checks", 0, "expected", "data"), [[[1]]]),
    ],
)
def test_invalid_reload_declarations_are_rejected_without_source_execution(
    path: tuple[str | int, ...], value: Any
) -> None:
    data = _data()
    target = data
    for key in path[:-1]:
        target = target[key]
    if value is _MISSING:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    with pytest.raises(WorkflowRegressionError):
        _contract(data)


@pytest.mark.parametrize("kind", ["array", "frame"])
def test_numeric_array_and_flat_frame_probes_are_accepted(kind: str) -> None:
    data = _data()
    probe = (
        {"kind": "array", "dtype": "float64", "data": [[0.0], [3.0]]}
        if kind == "array"
        else {
            "kind": "frame",
            "columns": ["x"],
            "data": [[0.0], [3.0]],
            "dtypes": ["float64"],
            "index": [0, 1],
            "index_name": None,
            "column_name": None,
        }
    )
    for check in data["model_checks"]:
        check["input"] = probe
    del data["fixtures"]["probe"]
    assert _contract(data).to_dict()["model_checks"][0]["input"]["kind"] == kind


def test_explicit_model_output_is_required_before_any_publication(tmp_path: Path) -> None:
    source = EXAMPLE / "workflow.ipynb"
    with pytest.raises(WorkflowRegressionError, match="explicit model_output"):
        generate_kedro_project(
            plan_notebook_path(source),
            tmp_path / "blocked",
            source_facts=analyze_notebook_path(source),
            regression_contract=_contract(_data()),
        )
    assert not (tmp_path / "blocked").exists()


def test_reports_declare_tests_without_claiming_runtime_success_or_full_object_oracles() -> None:
    source = EXAMPLE / "workflow.ipynb"
    files, _ = render_kedro_project(
        plan_notebook_path(source),
        source_facts=analyze_notebook_path(source),
        regression_contract=_contract(_data()),
        model_output="fitted_model",
    )
    report = json.loads(files[Path("regression-coverage.json")])
    assert report["model_reload_checks"] == 2
    assert report["model_reload_methods"] == ["predict", "predict_proba"]
    assert report["model_reload_status"] == report["execution_status"] == "not_run"
    assert "fitted_model" in report["missing_pipeline_outputs"]
    metadata = json.loads(files[Path("model-output.json")])
    assert metadata["generated_regressions_validate_storage"] is True
    assert metadata["reload_validation_status"] == "not_run"
    assert metadata["runtime_type_status"] == "not_verified"
    assert "infer an object oracle" not in files[Path("MODEL_OUTPUT.md")]
    assert Path("tests/_model_reload_worker.py") in files


def test_empty_model_checks_add_no_worker_or_storage_claims() -> None:
    data = _data()
    data["model_checks"] = []
    del data["fixtures"]["probe"]
    source = EXAMPLE / "workflow.ipynb"
    files, _ = render_kedro_project(
        plan_notebook_path(source),
        source_facts=analyze_notebook_path(source),
        regression_contract=_contract(data),
        model_output="fitted_model",
    )
    assert Path("tests/_model_reload_worker.py") not in files
    assert "model_reload_checks" not in json.loads(files[Path("regression-coverage.json")])
    assert (
        json.loads(files[Path("model-output.json")])["generated_regressions_validate_storage"]
        is False
    )


def test_example_assets_are_reproducible_and_writer_refuses_overwrite(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "reload_example_builder", ROOT / "tools/build_model_reload_example.py"
    )
    assert spec is not None
    assert spec.loader is not None
    builder: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    files = builder.build_files()
    for relative, content in files.items():
        assert (EXAMPLE / relative).read_bytes() == content.encode()
    write_project(tmp_path / "example", files)
    with pytest.raises(ProjectGenerationError):
        write_project(tmp_path / "example", files)
