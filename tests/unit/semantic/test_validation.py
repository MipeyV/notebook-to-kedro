"""Unit tests for conversion plan validation."""

import pytest

from notebook_to_kedro.exceptions import ConversionPlanValidationError
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue, TaskCandidate
from notebook_to_kedro.semantic import validate_conversion_plan


def _task(
    *,
    id_: str = "task-0001",
    name: str = "split_data",
    parameters: tuple[str, ...] = (),
) -> TaskCandidate:
    return TaskCandidate(
        id=id_,
        name=name,
        source_cell_ids=("cell-0001",),
        statement_ids=("cell-0001-stmt-0000",),
        inputs=("X", "y"),
        outputs=("X_train", "X_test"),
        source="X_train, X_test = split(X, y)",
        parameters=parameters,
    )


def _parameter(
    *,
    name: str = "split_data.test_size",
    function_argument: str = "split_data_test_size",
) -> ParameterValue:
    return ParameterValue(
        name=name,
        value=0.2,
        function_argument=function_argument,
        source_cell_id="cell-0001",
    )


def test_validate_conversion_plan_accepts_valid_plan() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(_task(parameters=("split_data.test_size",)),),
        catalog_datasets=(
            CatalogDataset(
                name="df",
                type="kedro_datasets.pandas.CSVDataset",
                filepath="data/01_raw/example.csv",
            ),
        ),
        parameters=(_parameter(),),
    )

    validate_conversion_plan(plan)


def test_validate_conversion_plan_rejects_blocking_diagnostics() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(),
        blocking_diagnostic_codes=("PY002",),
    )

    with pytest.raises(
        ConversionPlanValidationError,
        match="Invalid conversion plan: blocking diagnostics are present: PY002",
    ):
        validate_conversion_plan(plan)


def test_validate_conversion_plan_rejects_duplicate_names() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(
            _task(id_="task-0001", name="prepare"),
            _task(id_="task-0001", name="prepare"),
        ),
        catalog_datasets=(
            CatalogDataset(name="df", type="MemoryDataset", filepath="df"),
            CatalogDataset(name="df", type="MemoryDataset", filepath="df"),
        ),
        parameters=(
            _parameter(name="prepare.size", function_argument="prepare_size"),
            _parameter(name="prepare.size", function_argument="prepare_size"),
        ),
    )

    with pytest.raises(ConversionPlanValidationError) as error_info:
        validate_conversion_plan(plan)

    message = str(error_info.value)
    assert "duplicate task ID: task-0001" in message
    assert "duplicate task name: prepare" in message
    assert "duplicate catalog dataset name: df" in message
    assert "duplicate parameter name: prepare.size" in message
    assert "duplicate parameter function argument: prepare_size" in message


@pytest.mark.parametrize("task_name", ["bad-name", "_private"])
def test_validate_conversion_plan_rejects_invalid_task_names(task_name: str) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(_task(name=task_name),),
    )

    with pytest.raises(ConversionPlanValidationError, match="public Python identifier"):
        validate_conversion_plan(plan)


def test_validate_conversion_plan_rejects_unknown_task_parameters() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(_task(parameters=("split_data.test_size",)),),
        parameters=(),
    )

    with pytest.raises(
        ConversionPlanValidationError,
        match=r"task split_data references unknown parameter: split_data\.test_size",
    ):
        validate_conversion_plan(plan)
