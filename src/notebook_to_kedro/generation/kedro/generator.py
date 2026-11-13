"""Render a minimal Kedro project from a deterministic conversion plan."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from keyword import iskeyword
from pathlib import Path
from textwrap import indent
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import ConversionPlanValidationError, ProjectGenerationError
from notebook_to_kedro.generation.kedro.profiles import (
    DEFAULT_KEDRO_PROFILE,
    KedroArchitectureProfile,
    resolve_node_names,
)
from notebook_to_kedro.generation.parameters import ParameterReplacement
from notebook_to_kedro.generation.writer import write_project
from notebook_to_kedro.semantic.source_accounting import enforce_source_accounting
from notebook_to_kedro.semantic.validation import validate_conversion_plan

if TYPE_CHECKING:
    from collections.abc import Mapping

    from notebook_to_kedro.ir import (
        ConversionPlan,
        JsonPrimitive,
        NotebookFacts,
        ParameterValue,
        TaskCandidate,
    )

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
    architecture_profile: KedroArchitectureProfile | None = None,
    source_facts: NotebookFacts | None = None,
) -> tuple[Path, ...]:
    """Validate, compile and publish a minimal project without executing source code."""
    files, copies = render_kedro_project(
        plan,
        package_name=package_name,
        architecture_profile=architecture_profile,
        source_facts=source_facts,
    )
    return write_project(Path(output_path), files, copies)


def render_kedro_project(
    plan: ConversionPlan,
    *,
    package_name: str = DEFAULT_PACKAGE_NAME,
    architecture_profile: KedroArchitectureProfile | None = None,
    source_facts: NotebookFacts | None = None,
) -> tuple[dict[Path, str], tuple[tuple[Path, Path], ...]]:
    """Validate and render shared Kedro scaffolding without publishing or executing it."""
    if source_facts is not None:
        plan = enforce_source_accounting(source_facts, plan)
    try:
        validate_conversion_plan(plan)
    except ConversionPlanValidationError as error:
        raise ProjectGenerationError(str(error)) from error
    _require_valid_package_name(package_name)
    profile = DEFAULT_KEDRO_PROFILE if architecture_profile is None else architecture_profile
    node_names = None if architecture_profile is None else resolve_node_names(plan, profile)

    package_root = Path("src") / package_name
    pipeline_root = package_root / "pipelines" / profile.pipeline_name
    files = {
        Path("pyproject.toml"): _pyproject(package_name),
        Path("conf/local/.gitkeep"): "",
        package_root / "__init__.py": _package_init(),
        package_root / "settings.py": _settings(),
        package_root / "pipeline_registry.py": _pipeline_registry(
            package_name, profile.pipeline_name
        ),
        package_root / "pipelines" / "__init__.py": _package_init(),
        pipeline_root / "__init__.py": _notebook_pipeline_init(package_name, profile.pipeline_name),
        pipeline_root / "pipeline.py": _pipeline(
            plan, package_name, profile.pipeline_name, node_names
        ),
    }
    try:
        files[pipeline_root / "nodes.py"] = _nodes(plan, node_names)
        for path, content in files.items():
            if path.suffix == ".py":
                compile(content, path.as_posix(), "exec", dont_inherit=True)
    except (SyntaxError, ValueError) as error:
        raise ProjectGenerationError(f"Cannot render valid project Python: {error}") from error
    if plan.catalog_datasets:
        files[Path("conf/base/catalog.yml")] = _catalog(plan)
    if plan.parameters:
        files[Path("conf/base/parameters.yml")] = _parameters(plan)
    if architecture_profile is not None:
        files[Path("architecture-profile.json")] = _profile_manifest(plan, profile)
    copies = tuple(
        (Path(dataset.source_filepath), Path(dataset.filepath))
        for dataset in plan.catalog_datasets
        if dataset.source_filepath is not None
    )
    return files, copies


def _pyproject(package_name: str) -> str:
    return f"""[project]
name = "{package_name.replace("_", "-")}"
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "kedro>=1.5,<2",
    "kedro-datasets[pandas-csvdataset]>=8,<9",
    "pandas>=2.2,<4",
    "scikit-learn>=1.7,<2",
]

[tool.kedro]
package_name = "{package_name}"
project_name = "Generated Notebook"
kedro_init_version = "1.5.0"

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{package_name}"]
"""


def _package_init() -> str:
    return '"""Generated Kedro project package."""\n'


def _settings() -> str:
    return '"""Kedro settings for the generated project."""\n'


def _pipeline_registry(package_name: str, pipeline_name: str = "notebook_pipeline") -> str:
    return f'''"""Project pipeline registry."""

from kedro.pipeline import Pipeline

from {package_name}.pipelines.{pipeline_name} import create_pipeline


def register_pipelines() -> dict[str, Pipeline]:
    """Register generated project pipelines."""
    pipeline = create_pipeline()
    return {{"__default__": pipeline, "{pipeline_name}": pipeline}}
'''


def _notebook_pipeline_init(package_name: str, pipeline_name: str = "notebook_pipeline") -> str:
    return f'''"""Generated notebook pipeline."""

from {package_name}.pipelines.{pipeline_name}.pipeline import create_pipeline

__all__ = ["create_pipeline"]
'''


def _nodes(plan: ConversionPlan, node_names: Mapping[str, str] | None = None) -> str:
    sections = [*plan.imports, ""]
    sections.extend(
        render_node_function(
            task, function_name=None if node_names is None else node_names[task.id]
        )
        for task in plan.task_candidates
    )
    return "\n\n".join(section for section in sections if section).rstrip() + "\n"


def _profile_manifest(plan: ConversionPlan, profile: KedroArchitectureProfile) -> str:
    names = resolve_node_names(plan, profile)
    manifest = {
        "schema_version": "1.0",
        "profile": profile.to_dict(),
        "profile_sha256": profile.sha256,
        "notebook_path": plan.notebook_path,
        "nodes": [
            {
                "task_id": task.id,
                "source_name": task.name,
                "generated_name": names[task.id],
                "source_cell_ids": task.source_cell_ids,
                "statement_ids": task.statement_ids,
            }
            for task in plan.task_candidates
        ],
    }
    return json.dumps(manifest, sort_keys=True, indent=2) + "\n"


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


def render_node_function(task: TaskCandidate, *, function_name: str | None = None) -> str:
    """Render one validated plan task using V1 rules, without execution or file I/O."""
    function_parameters = ", ".join((*task.inputs, *_parameter_arguments(task)))
    body = indent(_parameterized_source(task).rstrip(), "    ")
    return_statement = _return_statement(task.outputs)
    name = task.name if function_name is None else function_name
    return f"""def {name}({function_parameters}):
{body}
    {return_statement}
"""


def _return_statement(outputs: tuple[str, ...]) -> str:
    if not outputs:
        return "return None"
    if len(outputs) == 1:
        return f"return {outputs[0]}"
    return f"return {', '.join(outputs)}"


def _pipeline(
    plan: ConversionPlan,
    package_name: str,
    pipeline_name: str = "notebook_pipeline",
    node_names: Mapping[str, str] | None = None,
) -> str:
    node_entries = "\n".join(
        _node_entry(entry, None if node_names is None else node_names[entry.task.id])
        for entry in _pipeline_entries(plan)
    )
    return f'''"""Generated Kedro pipeline."""

from kedro.pipeline import Pipeline, node

from {package_name}.pipelines.{pipeline_name} import nodes


def create_pipeline(**kwargs: object) -> Pipeline:
    """Create the generated notebook pipeline."""
    return Pipeline(
        [
{node_entries}
        ]
    )
'''


def _node_entry(entry: _PipelineEntry, node_name: str | None = None) -> str:
    inputs = _inputs_argument(entry)
    outputs = _outputs_argument(entry.outputs)
    name = entry.task.name if node_name is None else node_name
    return f"""            node(
                func=nodes.{name},
                inputs={inputs},
                outputs={outputs},
                name="{name}",
            ),"""


@dataclass(frozen=True, slots=True)
class _PipelineEntry:
    task: TaskCandidate
    inputs: dict[str, str]
    outputs: tuple[str, ...]
    parameters: dict[str, str]


def _pipeline_entries(plan: ConversionPlan) -> tuple[_PipelineEntry, ...]:
    entries: list[_PipelineEntry] = []
    latest_dataset_by_symbol = {dataset.name: dataset.name for dataset in plan.catalog_datasets}
    produced = set(latest_dataset_by_symbol)
    for task in plan.task_candidates:
        inputs = {symbol: latest_dataset_by_symbol.get(symbol, symbol) for symbol in task.inputs}
        outputs = tuple(
            _output_dataset(symbol, task, latest_dataset_by_symbol) for symbol in task.outputs
        )
        if len(outputs) != len(set(outputs)) or set(outputs) & produced:
            raise ProjectGenerationError("Generated dataset names have multiple producers")
        produced.update(outputs)
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
    replacements = parameter_replacements(task)
    return _replace_ranges(
        task.source,
        [(item.start_offset, item.end_offset, item.function_argument) for item in replacements],
    )


def parameter_replacements(task: TaskCandidate) -> tuple[ParameterReplacement, ...]:
    """Locate V1 parameter expressions without guessing from equal literal values."""
    if not task.parameters:
        return ()
    module = ast.parse(task.source)
    replacements: list[ParameterReplacement] = []
    names_by_suffix = {
        parameter_name.rsplit(".", maxsplit=1)[-1]: parameter_name
        for parameter_name in task.parameters
    }
    if len(names_by_suffix) != len(task.parameters):
        raise ValueError("ambiguous parameter suffixes in task")
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
                or parameter_suffix not in names_by_suffix
            ):
                continue
            replacements.append(
                _parameter_replacement(
                    task.source, keyword.value, names_by_suffix[parameter_suffix]
                )
            )
        if _call_method(node.func) == "fillna" and "fillna_values" in names_by_suffix and node.args:
            replacements.append(
                _parameter_replacement(task.source, node.args[0], names_by_suffix["fillna_values"])
            )
    return tuple(sorted(replacements, key=lambda item: item.start_offset))


def _parameter_replacement(source: str, node: ast.expr, name: str) -> ParameterReplacement:
    start = _offset(source, node.lineno, node.col_offset)
    end = _offset(source, node.end_lineno, node.end_col_offset)
    expression = source[start:end]
    return ParameterReplacement(
        parameter_name=name,
        function_argument=name.replace(".", "_"),
        source_expression=expression,
        value_type=type(ast.literal_eval(expression)).__name__,
        start_offset=start,
        end_offset=end,
    )


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
    lines = source.splitlines(keepends=True)
    # Python AST columns count UTF-8 bytes; string slicing counts Unicode characters.
    prefix = lines[line_number - 1].encode("utf-8")[:column].decode("utf-8")
    return sum(len(line) for line in lines[: line_number - 1]) + len(prefix)


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
    if not package_name.isidentifier() or package_name.startswith("_") or iskeyword(package_name):
        message = f"Invalid generated package name: {package_name}"
        raise ProjectGenerationError(message)
