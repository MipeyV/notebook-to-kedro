"""Private bounded-JSON worker for a statically validated whole notebook pipeline."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from notebook_to_kedro.evaluation.behavioral import TableBehaviorValue, behavior_value_to_dict
from notebook_to_kedro.evaluation.behavioral_execution import _array, _exact_keys, _object, _string
from notebook_to_kedro.evaluation.behavioral_worker import (
    _base_result,
    _BoundedTextCapture,
    _exception_dict,
    _failure_result,
    _non_empty_string,
    _positive_int,
    _runtime_primitive,
    _serialize,
)
from notebook_to_kedro.evaluation.notebook_execution import (
    _PACKAGE,
    NOTEBOOK_PIPELINE_EXECUTION_VERSION,
    NotebookObservation,
)
from notebook_to_kedro.evaluation.notebook_sources import _reject_constant
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.evaluation.behavioral import BehaviorValue

_ARGUMENT_COUNT = 5


class _ObservationError(Exception):
    """Separate unsupported observations from failures of pipeline business code."""


def _files(root: Path, payload: object) -> None:
    root.mkdir()
    seen = set()
    for value in _array(payload, "snapshot files"):
        row = _object(value, "snapshot file")
        _exact_keys(row, {"path", "sha256", "data"}, "snapshot file")
        relative = _non_empty_string(row["path"], "snapshot path")
        path = (root / relative).resolve()
        if (
            Path(relative).is_absolute()
            or not path.is_relative_to(root.resolve())
            or path == root.resolve()
            or path in seen
        ):
            raise ValueError("snapshot paths must be unique files contained in the worker root")
        seen.add(path)
        data = base64.b64decode(_string(row["data"], "snapshot data"), validate=True)
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("snapshot bytes do not match their hash")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _observe(value: object, kind: str) -> BehaviorValue:
    if kind == "series":
        pd = importlib.import_module("pandas")
        if not isinstance(value, pd.Series):
            raise ValueError("series observation requires a pandas Series")
        series = cast("Any", value)
        value = series.to_frame(name="value")
    if kind == "decision_tree":
        tree = importlib.import_module("sklearn.tree")
        if type(value) is not tree.DecisionTreeClassifier:
            raise ValueError("decision_tree observation requires DecisionTreeClassifier")
        model = cast("Any", value)
        return _serialize(
            {
                "class": type(value).__name__,
                "max_depth": model.max_depth,
                "random_state": model.random_state,
                "classes": model.classes_.tolist(),
                "training_samples": int(model.tree_.n_node_samples[0]),
                "feature_count": int(model.n_features_in_),
            }
        )
    pd = importlib.import_module("pandas")
    if isinstance(value, pd.DataFrame):
        frame = cast("Any", value)
        if not all(isinstance(column, str) for column in frame.columns):
            raise ValueError("observed table columns must be strings")
        # JSON null preserves missing cells alongside their original column dtype.
        return TableBehaviorValue(
            tuple(frame.columns),
            tuple(str(dtype) for dtype in frame.dtypes),
            tuple(
                tuple(None if pd.isna(cell) else _runtime_primitive(cell) for cell in row)
                for row in frame.to_numpy(dtype=object).tolist()
            ),
            tuple(_runtime_primitive(index) for index in frame.index.tolist()),
        )
    return _serialize(value)


def _observation_failure(error: BaseException) -> bool:
    cause: BaseException | None = error
    for _ in range(16):
        if cause is None:
            break
        if isinstance(cause, _ObservationError):
            return True
        cause = cause.__cause__ or cause.__context__
    return False


def _run_project(
    project: Path,
    nodes: list[object],
    targets: tuple[NotebookObservation, ...],
) -> tuple[dict[str, BehaviorValue], tuple[Any, Any, Any]]:
    # These imports are optional evaluation dependencies, loaded only in the worker.
    config = importlib.import_module("kedro.config")
    io = importlib.import_module("kedro.io")
    runner = importlib.import_module("kedro.runner")
    sys.path.insert(0, str(project / "src"))
    os.chdir(project)
    registered = importlib.import_module(f"{_PACKAGE}.pipeline_registry").register_pipelines()
    pipeline = registered["notebook_pipeline"]
    actual = [
        {"name": node.name, "inputs": node.inputs, "outputs": node.outputs}
        for node in pipeline.nodes
    ]
    if registered["__default__"] is not pipeline or sorted(
        actual, key=lambda row: row["name"]
    ) != sorted(
        nodes,
        key=lambda value: _non_empty_string(_object(value, "node")["name"], "node name"),
    ):
        raise ValueError("generated pipeline wiring does not match the frozen requests")
    loader = config.OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = io.DataCatalog.from_config(loader["catalog"])
    parameters = loader["parameters"]
    observed: dict[str, BehaviorValue] = {}
    by_name = {target.dataset: target for target in targets}

    memory_dataset = cast("Any", io.MemoryDataset)

    class ObservedDataset(memory_dataset):  # type: ignore[misc, valid-type]
        def __init__(self, name: str) -> None:
            super().__init__(copy_mode="assign")
            self.name = name

        def save(self, data: object) -> None:
            if self.name in by_name:
                try:
                    observed[self.name] = _observe(data, by_name[self.name].kind)
                except Exception as error:
                    raise _ObservationError(str(error)) from error
            super().save(data)

    for name in pipeline.datasets() - set(loader["catalog"]):
        catalog[name] = ObservedDataset(name)
    for name, value in parameters.items():
        catalog.save(f"params:{name}", value)
    return observed, (runner.SequentialRunner(), pipeline, catalog)


def run_notebook_worker_payload(payload: object) -> dict[str, object]:
    """Run one trusted parent envelope; direct calls are private and not a validation gate."""
    data = _object(payload, "notebook worker request")
    _exact_keys(
        data,
        {
            "schema_version",
            "case_id",
            "node_code_case_id",
            "source_files",
            "project_files",
            "observations",
            "nodes",
            "max_capture_bytes",
        },
        "notebook worker request",
    )
    if data["schema_version"] != NOTEBOOK_PIPELINE_EXECUTION_VERSION:
        raise ValueError("unsupported notebook worker version")
    case = _non_empty_string(data["case_id"], "case_id")
    identity = _non_empty_string(data["node_code_case_id"], "node_code_case_id")
    limit = _positive_int(data["max_capture_bytes"], "max_capture_bytes")
    targets = []
    for item in _array(data["observations"], "observations"):
        row = _object(item, "observation")
        _exact_keys(row, {"dataset", "kind"}, "observation")
        targets.append(NotebookObservation(row["dataset"], row["kind"]))  # type: ignore[arg-type]
    if not targets or len({target.dataset for target in targets}) != len(targets):
        raise ValueError("worker requires unique non-empty observations")
    nodes = _array(data["nodes"], "nodes")
    result = _base_result(case, identity)
    stdout = _BoundedTextCapture(limit)
    stderr = _BoundedTextCapture(limit)
    try:
        _files(Path.cwd() / "worker_inputs", data["source_files"])
        project = Path.cwd() / "worker_project"
        _files(project, data["project_files"])
        with redirect_stdout(stdout), redirect_stderr(stderr):
            observed, execution = _run_project(project, nodes, tuple(targets))
    except BaseException as error:
        return _failure_result(result, "setup_failure", error, stdout, stderr)
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            runner, pipeline, catalog = execution
            runner.run(pipeline, catalog)
    except BaseException as error:
        if _observation_failure(error):
            return _failure_result(result, "serialization_failure", error, stdout, stderr)
        result.update(status="exception", exception=_exception_dict(error))
    else:
        if set(observed) != {target.dataset for target in targets}:
            return _failure_result(
                result, "serialization_failure", ValueError("missing observations"), stdout, stderr
            )
        result.update(
            status="success",
            outputs=[
                {
                    "output_name": target.dataset,
                    "value": behavior_value_to_dict(observed[target.dataset]),
                }
                for target in targets
            ],
        )
    result.update(
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
        stdout_truncated=stdout.truncated,
        stderr_truncated=stderr.truncated,
    )
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    """Verify a bounded request and publish only bounded typed JSON observations."""
    args = tuple(sys.argv[1:] if arguments is None else arguments)
    if len(args) != _ARGUMENT_COUNT:
        return 2
    try:
        request_limit, result_limit = int(args[2]), int(args[3])
        if request_limit <= 0 or result_limit <= 0:
            return 2
        with Path(args[0]).open("rb") as stream:
            raw = stream.read(request_limit + 1)
        if len(raw) > request_limit or hashlib.sha256(raw).hexdigest() != args[4]:
            return 3
        payload = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        result = run_notebook_worker_payload(payload)
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False).encode("utf-8")
        if len(encoded) > result_limit:
            fallback = _base_result(result["case_id"], result["node_code_case_id"])  # type: ignore[arg-type]
            fallback.update(
                status="serialization_failure",
                diagnostic_message="worker observation exceeds max_result_bytes",
            )
            encoded = json.dumps(fallback).encode("utf-8")
            if len(encoded) > result_limit:
                return 3
        Path(args[1]).write_bytes(encoded)
    except (OSError, TypeError, ValueError):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
