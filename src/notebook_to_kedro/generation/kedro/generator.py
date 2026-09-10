"""Render a minimal Kedro project from a deterministic conversion plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import indent
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, TaskCandidate

DEFAULT_PACKAGE_NAME = "generated_notebook"


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

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return tuple(files)


def _pyproject(package_name: str) -> str:
    return f"""[project]
name = "{package_name.replace("_", "-")}"
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "kedro>=1.5,<2",
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


def _node_function(task: TaskCandidate) -> str:
    parameters = ", ".join(task.inputs)
    body = indent(task.source.rstrip(), "    ")
    return_statement = _return_statement(task.outputs)
    return f"""def {task.name}({parameters}):
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
    inputs = _inputs_argument(entry.inputs)
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


def _pipeline_entries(plan: ConversionPlan) -> tuple[_PipelineEntry, ...]:
    entries: list[_PipelineEntry] = []
    latest_dataset_by_symbol: dict[str, str] = {}
    for task in plan.task_candidates:
        inputs = {symbol: latest_dataset_by_symbol.get(symbol, symbol) for symbol in task.inputs}
        outputs = tuple(
            _output_dataset(symbol, task, latest_dataset_by_symbol) for symbol in task.outputs
        )
        latest_dataset_by_symbol.update(zip(task.outputs, outputs, strict=True))
        entries.append(_PipelineEntry(task=task, inputs=inputs, outputs=outputs))
    return tuple(entries)


def _output_dataset(
    symbol: str, task: TaskCandidate, latest_dataset_by_symbol: dict[str, str]
) -> str:
    if symbol in latest_dataset_by_symbol:
        return f"{symbol}__{task.name}"
    return symbol


def _inputs_argument(values: dict[str, str]) -> str:
    if not values:
        return "None"
    if all(parameter == dataset for parameter, dataset in values.items()):
        return _quoted_sequence(tuple(values))
    return repr(values)


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
