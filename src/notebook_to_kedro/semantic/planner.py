"""Deterministic task planning from notebook facts."""

from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from notebook_to_kedro.ir import (
    CallFacts,
    CatalogDataset,
    CellFacts,
    CellKind,
    ConversionPlan,
    NotebookFacts,
    ParameterValue,
    PlanDiagnostic,
    SymbolKind,
    TaskCandidate,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from notebook_to_kedro.ir import PlanParameterValue

PLANNER_VERSION = "0.1.0"
SUPPORTED_PARAMETER_KEYWORDS = {
    "RandomForestClassifier": frozenset({"n_estimators", "random_state"}),
    "StandardScaler": frozenset({"with_mean", "with_std"}),
    "train_test_split": frozenset({"test_size", "random_state"}),
}


def plan_tasks(facts: NotebookFacts) -> ConversionPlan:
    """Propose one task candidate per analyzable code cell with data outputs."""
    catalog_datasets = _catalog_datasets(facts)
    catalog_dataset_names = {dataset.name for dataset in catalog_datasets}
    import_names = {symbol.name for symbol in facts.symbols if symbol.kind is SymbolKind.IMPORT}
    data_symbols = {symbol.name for symbol in facts.symbols if symbol.kind is not SymbolKind.IMPORT}
    task_names_by_cell = _task_names_by_cell(
        facts,
        import_names=import_names,
        data_symbols=data_symbols,
        catalog_dataset_names=catalog_dataset_names,
    )
    parameters = _parameters(facts, task_names_by_cell)
    blocking_codes = _blocking_diagnostic_codes(facts)
    if blocking_codes:
        return ConversionPlan(
            schema_version="1.0",
            planner_version=PLANNER_VERSION,
            notebook_path=facts.notebook.path,
            task_candidates=(),
            imports=_imports(facts),
            catalog_datasets=catalog_datasets,
            parameters=parameters,
            diagnostics=_blocking_plan_diagnostics(blocking_codes),
            blocking_diagnostic_codes=blocking_codes,
        )

    parameters_by_cell = _parameter_names_by_cell(parameters)
    dependency_inputs_by_cell: dict[int, set[str]] = {}
    for dependency in facts.dependencies:
        dependency_inputs_by_cell.setdefault(dependency.consumer.cell_index, set()).add(
            dependency.symbol
        )

    candidates = tuple(
        candidate
        for cell in facts.cells
        if (
            candidate := _task_candidate(
                cell,
                _PlanningContext(
                    import_names=import_names,
                    data_symbols=data_symbols,
                    dependency_inputs_by_cell=dependency_inputs_by_cell,
                    catalog_dataset_names=catalog_dataset_names,
                    parameters_by_cell=parameters_by_cell,
                    task_names_by_cell=task_names_by_cell,
                ),
            )
        )
        is not None
    )
    return ConversionPlan(
        schema_version="1.0",
        planner_version=PLANNER_VERSION,
        notebook_path=facts.notebook.path,
        task_candidates=candidates,
        imports=_imports(facts),
        catalog_datasets=catalog_datasets,
        parameters=parameters,
        diagnostics=_plan_diagnostics(candidates, catalog_dataset_names),
    )


@dataclass(frozen=True, slots=True)
class _PlanningContext:
    import_names: set[str]
    data_symbols: set[str]
    dependency_inputs_by_cell: dict[int, set[str]]
    catalog_dataset_names: set[str]
    parameters_by_cell: dict[str, tuple[str, ...]]
    task_names_by_cell: dict[str, str]


def _task_candidate(
    cell: CellFacts,
    context: _PlanningContext,
) -> TaskCandidate | None:
    if cell.kind is not CellKind.CODE or not cell.statements:
        return None

    outputs = _task_outputs(
        cell,
        import_names=context.import_names,
        data_symbols=context.data_symbols,
        catalog_dataset_names=context.catalog_dataset_names,
    )
    if not outputs:
        return None

    dependency_inputs = context.dependency_inputs_by_cell.get(cell.index, set())
    inputs = tuple(
        name
        for name in cell.reads
        if name in dependency_inputs
        or (
            name not in outputs
            and name in context.data_symbols
            and name not in context.import_names
        )
    )
    return TaskCandidate(
        id=f"task-{cell.index:04d}",
        name=context.task_names_by_cell[cell.id],
        source_cell_ids=(cell.id,),
        statement_ids=tuple(statement.id for statement in cell.statements),
        inputs=_ordered_names(inputs),
        outputs=outputs,
        source=cell.source,
        parameters=context.parameters_by_cell.get(cell.id, ()),
        diagnostic_codes=cell.diagnostic_codes,
    )


def _task_names_by_cell(
    facts: NotebookFacts,
    *,
    import_names: set[str],
    data_symbols: set[str],
    catalog_dataset_names: set[str],
) -> dict[str, str]:
    names_by_cell: dict[str, str] = {}
    used_names: dict[str, int] = {}
    current_heading: str | None = None
    for cell in facts.cells:
        if cell.kind is CellKind.MARKDOWN:
            current_heading = _markdown_heading(cell.source) or current_heading
            continue
        if not _task_outputs(
            cell,
            import_names=import_names,
            data_symbols=data_symbols,
            catalog_dataset_names=catalog_dataset_names,
        ):
            continue
        base_name = _pattern_name(cell) or current_heading or f"cell_{cell.index:04d}"
        names_by_cell[cell.id] = _unique_task_name(_slug_identifier(base_name), used_names)
    return names_by_cell


def _task_outputs(
    cell: CellFacts,
    *,
    import_names: set[str],
    data_symbols: set[str],
    catalog_dataset_names: set[str],
) -> tuple[str, ...]:
    if cell.kind is not CellKind.CODE or not cell.statements:
        return ()
    return tuple(
        name
        for name in cell.writes
        if name in data_symbols and name not in import_names and name not in catalog_dataset_names
    )


def _markdown_heading(source: str) -> str | None:
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _pattern_name(cell: CellFacts) -> str | None:
    qualified_names = {call.qualified_name for call in cell.calls}
    methods = {call.method for call in cell.calls if call.method is not None}
    name = None
    if "train_test_split" in qualified_names:
        name = "split_data"
    elif {"fit_transform", "transform"} & methods and any(
        name.endswith("_scaled") for name in cell.writes
    ):
        name = "scale_features"
    elif "fillna" in methods and cell.writes == ("df",):
        name = "impute_missing_values"
    elif "assign" in methods and cell.writes == ("df",):
        name = "engineer_features"
    elif "dropna" in methods and cell.writes == ("df",):
        name = "clean_data"
    elif "accuracy" in cell.writes or any(
        name.endswith("accuracy_score") for name in qualified_names
    ):
        name = "evaluate_model"
    elif "predictions" in cell.writes or "predict" in methods:
        name = "predict"
    elif "model" in cell.writes and (
        "fit" in methods or "RandomForestClassifier" in qualified_names
    ):
        name = "train_model"
    elif any(
        name.endswith(("load_iris", "load_wine", "load_breast_cancer")) for name in qualified_names
    ):
        name = "load_data"
    return name


def _slug_identifier(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        return "task"
    if slug[0].isdigit():
        return f"task_{slug}"
    return slug


def _unique_task_name(base_name: str, used_names: dict[str, int]) -> str:
    count = used_names.get(base_name, 0) + 1
    used_names[base_name] = count
    if count == 1:
        return base_name
    return f"{base_name}_{count}"


def _blocking_diagnostic_codes(facts: NotebookFacts) -> tuple[str, ...]:
    return _ordered_names(
        diagnostic.code for diagnostic in facts.diagnostics if diagnostic.blocking
    )


def _blocking_plan_diagnostics(codes: tuple[str, ...]) -> tuple[PlanDiagnostic, ...]:
    return tuple(
        PlanDiagnostic(
            code="PD000",
            severity="error",
            message=f"Blocking source diagnostic prevents task planning: {code}.",
        )
        for code in codes
    )


def _plan_diagnostics(
    candidates: tuple[TaskCandidate, ...], catalog_dataset_names: set[str]
) -> tuple[PlanDiagnostic, ...]:
    diagnostics: list[PlanDiagnostic] = []
    produced_symbols = set(catalog_dataset_names)
    for task in candidates:
        diagnostics.extend(_task_review_diagnostics(task, produced_symbols))
        produced_symbols.update(task.outputs)
    return tuple(diagnostics)


def _task_review_diagnostics(
    task: TaskCandidate, produced_symbols: set[str]
) -> tuple[PlanDiagnostic, ...]:
    diagnostics: list[PlanDiagnostic] = []
    if re.fullmatch(r"cell_\d{4}", task.name):
        diagnostics.append(
            PlanDiagnostic(
                code="PD001",
                severity="warning",
                message=f"Task {task.name} uses a fallback cell-based name.",
                task_id=task.id,
            )
        )
    diagnostics.extend(
        PlanDiagnostic(
            code="PD002",
            severity="warning",
            message=f"Task {task.name} inherits source diagnostic {code}.",
            task_id=task.id,
        )
        for code in task.diagnostic_codes
    )
    diagnostics.extend(
        PlanDiagnostic(
            code="PD003",
            severity="warning",
            message=f"Task {task.name} reads unresolved external input {input_name}.",
            task_id=task.id,
        )
        for input_name in task.inputs
        if input_name not in produced_symbols
    )
    if not task.outputs:
        diagnostics.append(
            PlanDiagnostic(
                code="PD004",
                severity="warning",
                message=f"Task {task.name} has no data outputs.",
                task_id=task.id,
            )
        )
    return tuple(diagnostics)


def _imports(facts: NotebookFacts) -> tuple[str, ...]:
    return tuple(
        statement.source
        for cell in facts.cells
        for statement in cell.statements
        if statement.ast_type in {"Import", "ImportFrom"}
    )


def _catalog_datasets(facts: NotebookFacts) -> tuple[CatalogDataset, ...]:
    datasets: list[CatalogDataset] = []
    for cell in facts.cells:
        calls_by_id = {call.id: call for call in cell.calls}
        for statement in cell.statements:
            if len(statement.writes) != 1 or len(statement.call_ids) != 1:
                continue
            call = calls_by_id[statement.call_ids[0]]
            if _is_csv_loader_call(call):
                source_filepath = _source_filepath(facts.notebook.path, _csv_filepath(call))
                datasets.append(
                    CatalogDataset(
                        name=statement.writes[0],
                        type="kedro_datasets.pandas.CSVDataset",
                        filepath=f"data/01_raw/{PurePosixPath(source_filepath).name}",
                        source_filepath=source_filepath,
                    )
                )
    return tuple(datasets)


def _parameters(
    facts: NotebookFacts, task_names_by_cell: dict[str, str]
) -> tuple[ParameterValue, ...]:
    parameters: list[ParameterValue] = []
    for cell in facts.cells:
        task_name = task_names_by_cell.get(cell.id)
        if task_name is None:
            continue
        for call in cell.calls:
            parameters.extend(_call_parameters(cell, call, task_name))
    return tuple(parameters)


def _call_parameters(
    cell: CellFacts, call: CallFacts, task_name: str
) -> tuple[ParameterValue, ...]:
    parameters: list[ParameterValue] = []
    supported_keywords = SUPPORTED_PARAMETER_KEYWORDS.get(call.qualified_name, frozenset())
    supported_keyword_names = supported_keywords | _pandas_supported_keyword_names(call)
    for keyword in call.keyword_arguments:
        parameter_name = _keyword_parameter_name(call, keyword.name)
        if keyword.name not in supported_keyword_names or parameter_name is None:
            continue
        value = _literal_parameter_value(
            keyword.source, allow_collections=keyword.name in _pandas_supported_keyword_names(call)
        )
        if value is not None:
            parameters.append(_parameter_value(cell, task_name, parameter_name, value))
    fillna_value = _fillna_positional_value(call)
    if fillna_value is not None:
        parameters.append(_parameter_value(cell, task_name, "fillna_values", fillna_value))
    return tuple(parameters)


def _pandas_supported_keyword_names(call: CallFacts) -> frozenset[str]:
    if call.method == "drop":
        return frozenset({"columns"})
    if call.method == "fillna":
        return frozenset({"value"})
    return frozenset()


def _keyword_parameter_name(call: CallFacts, keyword_name: str) -> str | None:
    if call.method == "drop" and keyword_name == "columns":
        return "drop_columns"
    if call.method == "fillna" and keyword_name == "value":
        return "fillna_values"
    return keyword_name


def _fillna_positional_value(call: CallFacts) -> PlanParameterValue | None:
    if call.method != "fillna" or not call.positional_argument_sources:
        return None
    return _literal_parameter_value(call.positional_argument_sources[0], allow_collections=True)


def _parameter_value(
    cell: CellFacts, task_name: str, parameter_name: str, value: PlanParameterValue
) -> ParameterValue:
    return ParameterValue(
        name=f"{task_name}.{parameter_name}",
        value=value,
        function_argument=f"{task_name}_{parameter_name}",
        source_cell_id=cell.id,
    )


def _literal_parameter_value(
    source: str, *, allow_collections: bool = False
) -> PlanParameterValue | None:
    try:
        value = ast.literal_eval(source)
    except (ValueError, SyntaxError):
        return None
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if not allow_collections:
        return None
    if isinstance(value, list | tuple) and all(_is_json_primitive(item) for item in value):
        return tuple(value)
    if isinstance(value, dict) and all(
        isinstance(key, str) and _is_json_primitive(item) for key, item in value.items()
    ):
        return tuple(value.items())
    return None


def _is_json_primitive(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _parameter_names_by_cell(parameters: tuple[ParameterValue, ...]) -> dict[str, tuple[str, ...]]:
    names_by_cell: dict[str, list[str]] = {}
    for parameter in parameters:
        names_by_cell.setdefault(parameter.source_cell_id, []).append(parameter.name)
    return {source_cell_id: tuple(names) for source_cell_id, names in names_by_cell.items()}


def _is_csv_loader_call(call: CallFacts) -> bool:
    return (
        call.qualified_name.endswith(".read_csv")
        and bool(call.literal_arguments)
        and isinstance(call.literal_arguments[0], str)
    )


def _csv_filepath(call: CallFacts) -> str:
    return str(call.literal_arguments[0])


def _source_filepath(notebook_path: str, filepath: str) -> str:
    source_path = PurePosixPath(filepath)
    if source_path.is_absolute():
        return source_path.as_posix()
    return posixpath.normpath((PurePosixPath(notebook_path).parent / source_path).as_posix())


def _ordered_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))
