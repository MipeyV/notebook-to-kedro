"""Render a minimal Kedro project from a deterministic conversion plan."""

from __future__ import annotations

import ast
import shutil
from dataclasses import dataclass
from pathlib import Path
from textwrap import indent
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, JsonPrimitive, ParameterValue, TaskCandidate

DEFAULT_PACKAGE_NAME = "generated_notebook"
PARAMETER_MAPPING_ITEM_LENGTH = 2
SUPPORTED_PARAMETER_KEYWORDS = {
    "RandomForestClassifier": frozenset({"n_estimators", "random_state"}),
    "StandardScaler": frozenset({"with_mean", "with_std"}),
    "train_test_split": frozenset({"test_size", "random_state"}),
}


def generate_kedro_project(
    plan: ConversionPlan,
    output_path: str | Path,
    *,
    package_name: str = DEFAULT_PACKAGE_NAME,
) -> tuple[Path, ...]:
    """Write a minimal Kedro project and return created file paths."""
    if plan.blocking_diagnostic_codes:
        codes = ", ".join(plan.blocking_diagnostic_codes)
        message = f"Cannot generate a project while blocking diagnostics are present: {codes}"
        raise ProjectGenerationError(message)
    _require_valid_package_name(package_name)

    root = Path(output_path)
    if root.exists():
        message = f"Destination already exists: {root}"
        raise ProjectGenerationError(message)

    package_root = root / "src" / package_name
    pipeline_root = package_root / "pipelines" / "notebook_pipeline"
    files = {
        root / "pyproject.toml": _pyproject(package_name),
        package_root / "__init__.py": _package_init(),
        package_root / "settings.py": _settings(),
        package_root / "pipeline_registry.py": _pipeline_registry(package_name),
        package_root / "pipelines" / "__init__.py": _package_init(),
        pipeline_root / "__init__.py": _notebook_pipeline_init(package_name),
        pipeline_root / "nodes.py": _nodes(plan),
        pipeline_root / "pipeline.py": _pipeline(plan, package_name),
    }
    if plan.catalog_datasets:
        files[root / "conf" / "base" / "catalog.yml"] = _catalog(plan)
    if plan.parameters:
        files[root / "conf" / "base" / "parameters.yml"] = _parameters(plan)

    created_paths: list[Path] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        created_paths.append(path)
    for source_path, target_path in _catalog_file_copies(plan, root):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        created_paths.append(target_path)
    return tuple(created_paths)


def _pyproject(package_name: str) -> str:
    return f"""[project]
name = "{package_name.replace("_", "-")}"
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "kedro>=1.5,<2",
    "kedro-datasets[pandas]>=8,<9",
    "pandas>=2.2,<4",
    "scikit-learn>=1.7,<2",
]

[tool.kedro]
package_name = "{package_name}"
project_name = "Generated Notebook"
kedro_init_version = "1.5.0"
"""


def _package_init() -> str:
    return '"""Generated Kedro project package."""\n'


def _settings() -> str:
    return '"""Kedro settings for the generated project."""\n'


def _pipeline_registry(package_name: str) -> str:
    return f'''"""Project pipeline registry."""

from kedro.pipeline import Pipeline

from {package_name}.pipelines.notebook_pipeline import create_pipeline


def register_pipelines() -> dict[str, Pipeline]:
    """Register generated project pipelines."""
    pipeline = create_pipeline()
    return {{"__default__": pipeline, "notebook_pipeline": pipeline}}
'''


def _notebook_pipeline_init(package_name: str) -> str:
    return f'''"""Generated notebook pipeline."""

from {package_name}.pipelines.notebook_pipeline.pipeline import create_pipeline

__all__ = ["create_pipeline"]
'''


def _nodes(plan: ConversionPlan) -> str:
    sections = [*plan.imports, ""]
    sections.extend(_node_function(task) for task in plan.task_candidates)
    return "\n\n".join(section for section in sections if section).rstrip() + "\n"


def _catalog(plan: ConversionPlan) -> str:
    return (
        "\n".join(
            _catalog_dataset(dataset.name, dataset.type, dataset.filepath)
            for dataset in plan.catalog_datasets
        ).rstrip()
        + "\n"
    )


def _catalog_dataset(name: str, type_: str, filepath: str) -> str:
    return f"""{name}:
  type: {type_}
  filepath: {filepath}
"""


def _parameters(plan: ConversionPlan) -> str:
    return "\n".join(_parameter(parameter) for parameter in plan.parameters) + "\n"


def _parameter(parameter: ParameterValue) -> str:
    return f"{parameter.name}: {_parameter_value(parameter.value)}"


def _parameter_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return repr(value)
    if _is_parameter_mapping(value):
        return _parameter_mapping(value)
    if _is_parameter_sequence(value):
        return _parameter_sequence(value)
    return str(value)


def _is_parameter_mapping(value: object) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, tuple)
        and len(item) == PARAMETER_MAPPING_ITEM_LENGTH
        and isinstance(item[0], str)
        for item in value
    )


def _parameter_mapping(value: object) -> str:
    items = tuple(
        cast("tuple[str, JsonPrimitive]", item) for item in cast("tuple[object, ...]", value)
    )
    return (
        "{"
        + ", ".join(f"{_parameter_value(key)}: {_parameter_value(item)}" for key, item in items)
        + "}"
    )


def _is_parameter_sequence(value: object) -> bool:
    return isinstance(value, tuple) and not _is_parameter_mapping(value)


def _parameter_sequence(value: object) -> str:
    items = cast("tuple[JsonPrimitive, ...]", value)
    return "[" + ", ".join(_parameter_value(item) for item in items) + "]"


def _catalog_file_copies(plan: ConversionPlan, root: Path) -> tuple[tuple[Path, Path], ...]:
    copies: list[tuple[Path, Path]] = []
    for dataset in plan.catalog_datasets:
        if dataset.source_filepath is None:
            continue
        source_path = Path(dataset.source_filepath)
        if not source_path.exists():
            message = f"Catalog source file does not exist: {dataset.source_filepath}"
            raise ProjectGenerationError(message)
        copies.append((source_path, root / dataset.filepath))
    return tuple(copies)


def _node_function(task: TaskCandidate) -> str:
    function_parameters = ", ".join((*task.inputs, *_parameter_arguments(task)))
    body = indent(_parameterized_source(task).rstrip(), "    ")
    return_statement = _return_statement(task.outputs)
    return f"""def {task.name}({function_parameters}):
{body}
    {return_statement}
"""


def _return_statement(outputs: tuple[str, ...]) -> str:
    if not outputs:
        return "return None"
    if len(outputs) == 1:
        return f"return {outputs[0]}"
    return f"return {', '.join(outputs)}"


def _pipeline(plan: ConversionPlan, package_name: str) -> str:
    node_entries = "\n".join(_node_entry(entry) for entry in _pipeline_entries(plan))
    return f'''"""Generated Kedro pipeline."""

from kedro.pipeline import Pipeline, node

from {package_name}.pipelines.notebook_pipeline import nodes


def create_pipeline(**kwargs: object) -> Pipeline:
    """Create the generated notebook pipeline."""
    return Pipeline(
        [
{node_entries}
        ]
    )
'''


def _node_entry(entry: _PipelineEntry) -> str:
    inputs = _inputs_argument(entry)
    outputs = _outputs_argument(entry.outputs)
    return f"""            node(
                func=nodes.{entry.task.name},
                inputs={inputs},
                outputs={outputs},
                name="{entry.task.name}",
            ),"""


@dataclass(frozen=True, slots=True)
class _PipelineEntry:
    task: TaskCandidate
    inputs: dict[str, str]
    outputs: tuple[str, ...]
    parameters: dict[str, str]


def _pipeline_entries(plan: ConversionPlan) -> tuple[_PipelineEntry, ...]:
    entries: list[_PipelineEntry] = []
    latest_dataset_by_symbol: dict[str, str] = {}
    for task in plan.task_candidates:
        inputs = {symbol: latest_dataset_by_symbol.get(symbol, symbol) for symbol in task.inputs}
        outputs = tuple(
            _output_dataset(symbol, task, latest_dataset_by_symbol) for symbol in task.outputs
        )
        latest_dataset_by_symbol.update(zip(task.outputs, outputs, strict=True))
        entries.append(
            _PipelineEntry(
                task=task,
                inputs=inputs,
                outputs=outputs,
                parameters=_task_parameter_inputs(plan, task),
            )
        )
    return tuple(entries)


def _output_dataset(
    symbol: str, task: TaskCandidate, latest_dataset_by_symbol: dict[str, str]
) -> str:
    if symbol in latest_dataset_by_symbol:
        return f"{symbol}__{task.name}"
    return symbol


def _inputs_argument(entry: _PipelineEntry) -> str:
    return _node_inputs_argument({**entry.inputs, **entry.parameters})


def _node_inputs_argument(values: dict[str, str]) -> str:
    if not values:
        return "None"
    if all(parameter == dataset for parameter, dataset in values.items()):
        return _quoted_sequence(tuple(values))
    return repr(values)


def _task_parameter_inputs(plan: ConversionPlan, task: TaskCandidate) -> dict[str, str]:
    parameters_by_name = {parameter.name: parameter for parameter in plan.parameters}
    return {
        parameters_by_name[name].function_argument: f"params:{name}" for name in task.parameters
    }


def _parameter_arguments(task: TaskCandidate) -> tuple[str, ...]:
    return tuple(name.replace(".", "_") for name in task.parameters)


def _parameterized_source(task: TaskCandidate) -> str:
    if not task.parameters:
        return task.source
    module = ast.parse(task.source)
    replacements: list[tuple[int, int, str]] = []
    supported_parameter_names = {
        parameter_name.rsplit(".", maxsplit=1)[1] for parameter_name in task.parameters
    }
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        supported_keywords = SUPPORTED_PARAMETER_KEYWORDS.get(
            _qualified_name(node.func), frozenset()
        )
        for keyword in node.keywords:
            parameter_suffix = _keyword_parameter_suffix(node, keyword.arg, supported_keywords)
            if (
                keyword.arg is None
                or parameter_suffix is None
                or parameter_suffix not in supported_parameter_names
            ):
                continue
            replacements.append(
                (
                    _offset(task.source, keyword.value.lineno, keyword.value.col_offset),
                    _offset(task.source, keyword.value.end_lineno, keyword.value.end_col_offset),
                    f"{task.name}_{parameter_suffix}",
                )
            )
        if (
            _call_method(node.func) == "fillna"
            and "fillna_values" in supported_parameter_names
            and node.args
        ):
            replacements.append(
                (
                    _offset(task.source, node.args[0].lineno, node.args[0].col_offset),
                    _offset(task.source, node.args[0].end_lineno, node.args[0].end_col_offset),
                    f"{task.name}_fillna_values",
                )
            )
    return _replace_ranges(task.source, replacements)


def _keyword_parameter_suffix(
    node: ast.Call, keyword: str | None, supported_keywords: frozenset[str]
) -> str | None:
    if keyword is None:
        return None
    method = _call_method(node.func)
    if method == "drop" and keyword == "columns":
        return "drop_columns"
    if method == "fillna" and keyword == "value":
        return "fillna_values"
    if keyword in supported_keywords:
        return keyword
    return None


def _qualified_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return type(node).__name__


def _call_method(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _offset(source: str, line_number: int | None, column: int | None) -> int:
    if line_number is None or column is None:
        return 0
    return sum(len(line) for line in source.splitlines(keepends=True)[: line_number - 1]) + column


def _replace_ranges(source: str, replacements: list[tuple[int, int, str]]) -> str:
    result = source
    for start, end, value in sorted(replacements, reverse=True):
        result = f"{result[:start]}{value}{result[end:]}"
    return result


def _outputs_argument(values: tuple[str, ...]) -> str:
    if not values:
        return "None"
    return _quoted_sequence(values)


def _quoted_sequence(values: tuple[str, ...]) -> str:
    if len(values) == 1:
        return f'"{values[0]}"'
    return repr(list(values))


def _require_valid_package_name(package_name: str) -> None:
    if not package_name.isidentifier() or package_name.startswith("_"):
        message = f"Invalid generated package name: {package_name}"
        raise ProjectGenerationError(message)
