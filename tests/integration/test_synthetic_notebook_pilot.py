"""Draft whole-notebook pilot: source contracts and real offline execution."""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import nbformat
import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner
from nbclient import NotebookClient
from nbformat import NotebookNode

from notebook_to_kedro import (
    analyze_notebook_path,
    generate_kedro_project,
    plan_notebook_path,
    validate_conversion_plan,
)
from notebook_to_kedro.evaluation import (
    NotebookBodyRecord,
    create_notebook_source_binding,
    prepare_notebook_body_requests,
    validate_notebook_body_batch,
    validate_source_bound_notebook_body_batch,
)
from notebook_to_kedro.exceptions import NodeCodeProviderError
from notebook_to_kedro.generation.code import NodeBodyResponse, NodeCodeRequest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIRECTORY = ROOT / "tests/fixtures/evaluation/pilots/customer_churn_v1"
CONTRACT = cast(
    "dict[str, Any]",
    json.loads((CONTRACT_DIRECTORY / "contract.json").read_text(encoding="utf-8")),
)
NOTEBOOK = ROOT / CONTRACT["notebook"]["path"]
ORDERS = ROOT / CONTRACT["sources"][1]["path"]
TABLE_NAMES = (*CONTRACT["expected_tables"], "X", "X_train", "X_test")
NEGATIVE_CONTROLS = CONTRACT["negative_controls"]
PANDAS = cast("Any", importlib.import_module("pandas"))


def _read_notebook() -> NotebookNode:
    return cast("NotebookNode", nbformat.read(NOTEBOOK, as_version=4))  # type: ignore[no-untyped-call]


def _frame_snapshot(frame: Any) -> dict[str, Any]:
    result = cast("dict[str, Any]", json.loads(frame.to_json(orient="split", double_precision=15)))
    result["dtypes"] = [str(dtype) for dtype in frame.dtypes]
    return result


def _frame(table: dict[str, Any]) -> Any:
    frame = PANDAS.DataFrame(table["data"], columns=table["columns"], index=table["index"])
    return frame.astype(dict(zip(table["columns"], table["dtypes"], strict=True)))


def _assert_table(actual: Any, expected: dict[str, Any]) -> None:
    policy = CONTRACT["comparison"]
    PANDAS.testing.assert_frame_equal(
        actual,
        _frame(expected),
        check_dtype=policy["check_dtypes"],
        check_exact=False,
        check_like=not policy["check_row_order"],
        atol=policy["numeric_atol"],
        rtol=policy["numeric_rtol"],
    )


def _snapshot(objects: dict[str, Any]) -> dict[str, Any]:
    model = objects["model"]
    return {
        "tables": {name: _frame_snapshot(objects[name]) for name in TABLE_NAMES},
        "series_metadata": {
            name: {"index": objects[name].index.tolist(), "dtype": str(objects[name].dtype)}
            for name in ("y", "y_train", "y_test", "holdout")
        },
        "y": objects["y"].tolist(),
        "y_train": objects["y_train"].tolist(),
        "y_test": objects["y_test"].tolist(),
        "holdout": objects["holdout"].tolist(),
        "predictions": objects["predictions"].tolist(),
        "confusion": objects["confusion"].tolist(),
        "prediction_dtype": str(objects["predictions"].dtype),
        "confusion_dtype": str(objects["confusion"].dtype),
        "accuracy": float(objects["accuracy"]),
        "model": {
            "class": type(model).__name__,
            "max_depth": model.max_depth,
            "random_state": model.random_state,
            "classes": model.classes_.tolist(),
            "training_samples": int(model.tree_.n_node_samples[0]),
            "feature_count": int(model.n_features_in_),
        },
    }


def _assert_expected(snapshot: dict[str, Any]) -> None:
    for name, expected in CONTRACT["expected_tables"].items():
        _assert_table(_frame(snapshot["tables"][name]), expected)
    features = _frame(CONTRACT["expected_tables"]["features"])
    expected_x = features[CONTRACT["feature_columns"]]
    for name, expected in (
        ("X", expected_x),
        ("X_train", expected_x.loc[CONTRACT["train_indices"]]),
        ("X_test", expected_x.loc[CONTRACT["test_indices"]]),
    ):
        _assert_table(_frame(snapshot["tables"][name]), _frame_snapshot(expected))
    assert snapshot["y"] == features["churned"].tolist()
    assert snapshot["y_train"] == CONTRACT["train_targets"]
    assert snapshot["y_test"] == CONTRACT["test_targets"]
    assert snapshot["holdout"] == [index in CONTRACT["test_indices"] for index in features.index]
    assert snapshot["series_metadata"] == {
        "y": {"index": features.index.tolist(), "dtype": "int64"},
        "y_train": {"index": CONTRACT["train_indices"], "dtype": "int64"},
        "y_test": {"index": CONTRACT["test_indices"], "dtype": "int64"},
        "holdout": {"index": features.index.tolist(), "dtype": "bool"},
    }
    assert snapshot["prediction_dtype"] == snapshot["confusion_dtype"] == "int64"
    for name in ("predictions", "confusion", "accuracy"):
        assert snapshot[name] == CONTRACT[name]
    assert snapshot["model"] == {
        "class": "DecisionTreeClassifier",
        "max_depth": 2,
        "random_state": 7,
        "classes": [0, 1],
        "training_samples": 8,
        "feature_count": 4,
    }


@pytest.fixture(scope="module")
def notebook_snapshot() -> dict[str, Any]:
    """Execute only the checked-in notebook with an in-memory observation cell."""
    notebook = _read_notebook()
    frames = ", ".join(f"{name!r}: {name}" for name in TABLE_NAMES)
    observer = f"""
import json as _pilot_json
_pilot_frames = {{{frames}}}
_pilot_snapshot = {{
    "tables": {{name: {{**_pilot_json.loads(frame.to_json(orient="split", double_precision=15)),
                       "dtypes": [str(dtype) for dtype in frame.dtypes]}}
               for name, frame in _pilot_frames.items()}},
    "series_metadata": {{name: {{"index": series.index.tolist(), "dtype": str(series.dtype)}}
                        for name, series in {{"y": y, "y_train": y_train,
                                             "y_test": y_test, "holdout": holdout}}.items()}},
    "y": y.tolist(), "y_train": y_train.tolist(), "y_test": y_test.tolist(),
    "holdout": holdout.tolist(), "predictions": predictions.tolist(),
    "confusion": confusion.tolist(), "accuracy": float(accuracy),
    "prediction_dtype": str(predictions.dtype), "confusion_dtype": str(confusion.dtype),
    "model": {{"class": type(model).__name__, "max_depth": model.max_depth,
              "random_state": model.random_state, "classes": model.classes_.tolist(),
              "training_samples": int(model.tree_.n_node_samples[0]),
              "feature_count": int(model.n_features_in_)}},
}}
print(_pilot_json.dumps(_pilot_snapshot, allow_nan=False, sort_keys=True))
"""
    notebook.cells.append(nbformat.v4.new_code_cell(observer))  # type: ignore[no-untyped-call]
    executed = NotebookClient(
        notebook, timeout=60, kernel_name="python3", allow_errors=False
    ).execute(cwd=str(NOTEBOOK.parent))
    stdout = "".join(
        output["text"] for output in executed.cells[-1].outputs if output.output_type == "stream"
    )
    assert hashlib.sha256(NOTEBOOK.read_bytes()).hexdigest() == CONTRACT["notebook"]["sha256"]
    return cast("dict[str, Any]", json.loads(stdout))


class _ObservedMemoryDataset(MemoryDataset):
    """Record node outputs before the runner releases normal in-memory datasets."""

    def __init__(self, name: str, observed: dict[str, Any]) -> None:
        super().__init__(copy_mode="assign")
        self.name = name
        self.observed = observed

    def save(self, data: Any) -> None:
        self.observed[self.name] = deepcopy(data)
        super().save(data)


def _run_project(
    destination: Path,
    monkeypatch: pytest.MonkeyPatch,
    control: dict[str, Any] | None = None,
    *,
    reference_module: str | None = None,
) -> dict[str, Any]:
    plan = plan_notebook_path(NOTEBOOK)
    package = "pilot_baseline"
    if control is not None:
        package = "pilot_" + control["id"].replace("-", "_")
        original = next(task for task in plan.task_candidates if task.name == control["task"])
        assert original.source.count(control["old"]) == 1
        changed = replace(original, source=original.source.replace(control["old"], control["new"]))
        plan = replace(
            plan,
            task_candidates=tuple(
                changed if task.id == original.id else task for task in plan.task_candidates
            ),
        )
    validate_conversion_plan(plan)
    if reference_module is not None:
        assert control is None
        package = "pilot_fixed_bodies"
    generate_kedro_project(plan, destination, package_name=package)
    if reference_module is not None:
        # Trusted fixture bodies only: this is not a consent-gated untrusted-code runner.
        (destination / "src" / package / "pipelines/notebook_pipeline/nodes.py").write_text(
            reference_module, encoding="utf-8", newline="\n"
        )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    module = importlib.import_module(f"{package}.pipeline_registry")
    registered = module.register_pipelines()
    pipeline = registered[CONTRACT["pipeline_id"]]
    assert registered["__default__"] is pipeline
    nodes = {node.name: node for node in pipeline.nodes}
    assert set(nodes) == {task["name"] for task in CONTRACT["tasks"]}
    for expected in CONTRACT["tasks"]:
        node = nodes[expected["name"]]
        assert node.inputs == expected["inputs"] + [
            f"params:{name}" for name in expected["parameters"]
        ]
        assert node.outputs == expected["outputs"]
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    assert (destination / "conf/base/catalog.yml").read_bytes() == (
        CONTRACT_DIRECTORY / "expected_catalog.yml"
    ).read_bytes()
    assert loader["parameters"] == CONTRACT["expected_parameters"]
    catalog = DataCatalog.from_config(loader["catalog"])
    datasets = importlib.import_module("kedro_datasets.pandas")
    assert isinstance(catalog["orders"], datasets.CSVDataset)
    observed: dict[str, Any] = {}
    for name in pipeline.datasets() - {"orders"}:
        catalog[name] = _ObservedMemoryDataset(name, observed)
    for name, value in loader["parameters"].items():
        catalog.save(f"params:{name}", value)
    assert (destination / "data/01_raw/orders.csv").read_bytes() == ORDERS.read_bytes()
    loaded = catalog.load("orders")
    assert list(loaded.columns) == CONTRACT["sources"][1]["columns"]
    assert len(loaded) == CONTRACT["sources"][1]["row_count"]
    SequentialRunner().run(pipeline, catalog)
    return observed


class _FixedPilotBodyProvider:
    """Echo trusted original cells with the one explicit planned literal substitution."""

    def __init__(self, requests: tuple[NodeCodeRequest, ...]) -> None:
        notebook = _read_notebook()
        self.requests: list[NodeCodeRequest] = []
        self.responses: dict[str, str | NodeCodeProviderError] = {}
        for request, task in zip(requests, CONTRACT["tasks"], strict=True):
            source = notebook.cells[task["cell_index"]].source
            if request.node_name == "join_customer_features":
                assert request.parameter_arguments == ("join_customer_features_fillna_values",)
                literal = '{"net_revenue": 0.0, "completed_orders": 0}'
                assert source.count(literal) == 1
                source = source.replace(literal, "join_customer_features_fillna_values")
            self.responses[request.request_id] = (
                "\n"
                + NodeBodyResponse("1.0", request.request_id, request.task_id, source).to_json()
                + "\n"
            )

    def complete(self, request: NodeCodeRequest) -> str:
        self.requests.append(request)
        response = self.responses[request.request_id]
        if isinstance(response, NodeCodeProviderError):
            raise response
        return response


def _fixed_records(
    requests: tuple[NodeCodeRequest, ...], provider: _FixedPilotBodyProvider
) -> tuple[NotebookBodyRecord, ...]:
    records = []
    for request in requests:
        try:
            raw = provider.complete(request)
        except NodeCodeProviderError as error:
            records.append(
                NotebookBodyRecord(request.request_id, provider_error=(error.code, error.message))
            )
        else:
            records.append(NotebookBodyRecord(request.request_id, raw))
    return tuple(records)


def test_pilot_fixed_body_batch_preserves_all_nine_requests() -> None:
    """Offline reference compatibility keeps the full denominator and exact evidence."""
    plan = plan_notebook_path(NOTEBOOK)
    requests = prepare_notebook_body_requests(plan)
    provider = _FixedPilotBodyProvider(requests)
    records = _fixed_records(requests, provider)
    report = validate_notebook_body_batch(plan, records)
    assert provider.requests == list(requests)
    assert report.planned_count == report.accepted_count == 9
    assert report.static_ready
    assert [proposal.record for proposal in report.proposals] == list(records)
    assert [request.node_name for request in requests] == [
        task["name"] for task in CONTRACT["tasks"]
    ]
    assert report.module_source is not None
    assert report.module_source.count("import pandas as pd") == 1
    assert report.module_source.count("import numpy as np") == 1
    assert CONTRACT["review"]["status"] == "pending"


@pytest.mark.parametrize("failure", ["provider", "schema", "body", "missing"])
def test_pilot_one_failed_body_prevents_complete_assembly(failure: str) -> None:
    """Eight valid nodes cannot become one statically ready pipeline by fallback."""
    plan = plan_notebook_path(NOTEBOOK)
    requests = prepare_notebook_body_requests(plan)
    provider = _FixedPilotBodyProvider(requests)
    request = requests[0]
    if failure == "provider":
        provider.responses[request.request_id] = NodeCodeProviderError(
            "fixed_error", "offline failure"
        )
    elif failure == "schema":
        provider.responses[request.request_id] = "{}"
    elif failure == "body":
        source = request.raw_source.replace("default_rng(7)", "default_rng(8)")
        provider.responses[request.request_id] = NodeBodyResponse(
            "1.0", request.request_id, request.task_id, source
        ).to_json()
    attempted = requests[1:] if failure == "missing" else requests
    records = _fixed_records(attempted, provider)
    report = validate_notebook_body_batch(plan, records)
    assert report.planned_count == 9
    assert report.accepted_count == 8
    assert report.module_source is None
    assert not report.static_ready
    assert (
        report.proposals[0].status
        == {
            "provider": "provider_error",
            "schema": "invalid_response",
            "body": "invalid_code",
            "missing": "not_requested",
        }[failure]
    )
    assert all(proposal.status == "accepted" for proposal in report.proposals[1:])
    assert provider.requests == list(attempted)


@pytest.mark.end_to_end
def test_pilot_fixed_bodies_execute_complete_pipeline_and_real_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, notebook_snapshot: dict[str, Any]
) -> None:
    """Trusted fixed assemblies match every observation without model calls or live injection."""
    plan = plan_notebook_path(NOTEBOOK)
    binding = create_notebook_source_binding(
        plan,
        project_root=ROOT,
        contract_path=CONTRACT_DIRECTORY / "contract.json",
        expected_catalog_path=CONTRACT_DIRECTORY / "expected_catalog.yml",
    )
    requests = binding.requests
    provider = _FixedPilotBodyProvider(requests)
    bound = validate_source_bound_notebook_body_batch(
        binding, _fixed_records(requests, provider), project_root=ROOT
    )
    assert bound.binding == binding
    assert json.loads(binding.review_json)["independent_human_review"] is False
    report = bound.batch
    assert report.static_ready
    assert report.module_source is not None
    generated = _snapshot(
        _run_project(tmp_path / "project", monkeypatch, reference_module=report.module_source)
    )
    _assert_expected(generated)
    assert generated == notebook_snapshot
    assert provider.requests == list(requests)


def test_pilot_identity_and_pending_review() -> None:
    """A draft synthetic pilot must not masquerade as independently approved evidence."""
    assert CONTRACT["schema_version"] == "pilot-draft-1"
    assert CONTRACT["review"]["status"] == "pending"
    assert CONTRACT["review"]["independent_human_review"] is False
    assert CONTRACT["review"]["reviewed_by"] is None
    assert CONTRACT["review"]["local_benchmark_provider_exposure"] == "none at fixture creation"
    for path, expected in (
        (NOTEBOOK, CONTRACT["notebook"]["sha256"]),
        (ORDERS, CONTRACT["sources"][1]["sha256"]),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    notebook = _read_notebook()
    nbformat.validate(notebook)
    assert len(notebook.cells) == CONTRACT["notebook"]["cell_count"]
    assert len({cell.id for cell in notebook.cells}) == len(notebook.cells)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            ast.parse(cell.source)
            assert cell.execution_count is None
            assert cell.outputs == []


def test_pilot_csv_preserves_deliberate_edge_cases() -> None:
    """Input provenance includes duplicates, refunds, missing values and an orphan key."""
    with ORDERS.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 21
    assert list(rows[0]) == CONTRACT["sources"][1]["columns"]
    assert [row["unit_price"] for row in rows if row["order_id"] == "O02"] == ["50", "999"]
    assert sum(row["status"] == "cancelled" for row in rows) == 2
    assert sum(row["units"] == "" for row in rows) == 1
    assert sum(row["discount"] == "" for row in rows) == 1
    assert sum(row["units"] == "-1" for row in rows) == 1
    assert sum(row["customer_id"] == "C99" for row in rows) == 1


def test_pilot_static_plan_matches_declared_boundaries_and_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All source statements are mapped once without notebook execution or data loading."""

    def forbid_execution(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Static analysis must not execute or load data")

    monkeypatch.setattr(NotebookClient, "execute", forbid_execution)
    monkeypatch.setattr(PANDAS, "read_csv", forbid_execution)
    facts = analyze_notebook_path(NOTEBOOK)
    plan = plan_notebook_path(NOTEBOOK)
    validate_conversion_plan(plan)
    notebook = _read_notebook()
    assert list(plan.blocking_diagnostic_codes) == CONTRACT["expected_blocking_diagnostic_codes"]
    assert len(plan.task_candidates) == len(CONTRACT["tasks"]) == 9
    covered: list[str] = []
    for task, expected in zip(plan.task_candidates, CONTRACT["tasks"], strict=True):
        index = expected["cell_index"]
        cell = notebook.cells[index]
        assert cell.id == expected["notebook_cell_id"]
        assert task.id == f"task-{index:04d}"
        assert task.source_cell_ids == (f"cell-{index:04d}",)
        assert task.source == cell.source
        assert list(task.statement_ids) == [
            f"cell-{index:04d}-stmt-{statement:04d}"
            for statement in range(expected["statement_count"])
        ]
        for field in ("name", "inputs", "outputs", "parameters", "diagnostic_codes"):
            actual = getattr(task, field)
            assert actual == (expected[field] if field == "name" else tuple(expected[field]))
        covered.extend(task.statement_ids)
    for index in (*CONTRACT["shared_import_cell_indices"], *CONTRACT["catalog_cell_indices"]):
        covered.extend(statement.id for statement in facts.cells[index].statements)
    assert len(covered) == len(set(covered)) == 35
    assert set(covered) == {statement.id for cell in facts.cells for statement in cell.statements}
    assert len(plan.catalog_datasets) == 1
    dataset = plan.catalog_datasets[0]
    source = CONTRACT["sources"][1]
    assert (dataset.name, dataset.type, dataset.filepath) == (
        source["name"],
        source["catalog_type"],
        source["generated_filepath"],
    )
    assert Path(cast("str", dataset.source_filepath)).resolve() == ORDERS
    assert "customers" not in {dataset.name for dataset in plan.catalog_datasets}
    simulation = CONTRACT["sources"][0]
    assert simulation["seed_expression"] in facts.cells[simulation["cell_index"]].source
    assert [parameter.name for parameter in plan.parameters] == list(
        CONTRACT["expected_parameters"]
    )


@pytest.mark.integration
def test_pilot_notebook_matches_hand_specified_expectations(
    notebook_snapshot: dict[str, Any],
) -> None:
    """A fresh Jupyter kernel matches independent expected tables, splits and metrics."""
    _assert_expected(notebook_snapshot)


@pytest.mark.end_to_end
def test_pilot_generated_project_matches_notebook_and_expectations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, notebook_snapshot: dict[str, Any]
) -> None:
    """Real CSV catalog loading and all nine generated nodes preserve the whole workflow."""
    generated = _snapshot(_run_project(tmp_path / "project", monkeypatch))
    _assert_expected(generated)
    assert generated == notebook_snapshot


@pytest.mark.end_to_end
@pytest.mark.parametrize("control", NEGATIVE_CONTROLS, ids=lambda control: control["id"])
def test_pilot_expectations_detect_controlled_semantic_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, control: dict[str, Any]
) -> None:
    """Trusted test-only mutants fail the oracle even when aggregate accuracy is unchanged."""
    if "expected_exception" in control:
        assert control["expected_exception"] == "AssertionError"
        with pytest.raises(AssertionError) as error:
            _run_project(tmp_path / "project", monkeypatch, control)
        assert error.traceback is not None
        assert error.traceback[-1].name == "evaluate_model"
    else:
        observed = _run_project(tmp_path / "project", monkeypatch, control)
        assert observed["accuracy"] == CONTRACT["accuracy"]
        table = control["observed_table"]
        with pytest.raises(AssertionError):
            _assert_table(observed[table], CONTRACT["expected_tables"][table])
