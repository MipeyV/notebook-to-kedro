"""Adapt checked functional workflows to the shared Kedro renderer and project writer."""

from __future__ import annotations

import ast
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.analysis.functional_sources import analyze_functional_blocks_path
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.generation.kedro.profiles import DEFAULT_KEDRO_PROFILE
from notebook_to_kedro.generation.kedro.regression import render_workflow_regression_tests
from notebook_to_kedro.generation.writer import write_project
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue, TaskCandidate
from notebook_to_kedro.semantic.functional_workflow import plan_functional_workflow

if TYPE_CHECKING:
    from notebook_to_kedro.generation.kedro.profiles import KedroArchitectureProfile
    from notebook_to_kedro.generation.kedro.regression_contract import WorkflowRegressionContract
    from notebook_to_kedro.semantic.functional_config import FunctionalWorkflowConfiguration
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan


def plan_functional_workflow_path(
    path: str | Path,
    configuration: FunctionalWorkflowConfiguration,
    *,
    project_root: str | Path | None = None,
) -> FunctionalWorkflowPlan:
    """Inspect a script/notebook and validate the configured entrypoint without execution."""
    return plan_functional_workflow(
        analyze_functional_blocks_path(path, project_root=project_root), configuration
    )


def _conversion_plan(plan: FunctionalWorkflowPlan, root: Path, package_name: str) -> ConversionPlan:
    parameters = set(dict(plan.configuration.parameters))
    tasks = tuple(
        TaskCandidate(
            id=step.id,
            name=step.name,
            source_cell_ids=tuple(
                unit.cell_id
                for unit in plan.analysis.sources
                if unit.id == step.span.unit_id and unit.cell_id is not None
            ),
            statement_ids=(step.id,),
            inputs=tuple(
                dict.fromkeys(value for _, value in step.inputs if value not in parameters)
            ),
            outputs=(step.output,),
            source=step.source,
            parameters=tuple(
                dict.fromkeys(value for _, value in step.inputs if value in parameters)
            ),
        )
        for step in plan.steps
    )
    catalog: list[CatalogDataset] = []
    for argument, filepath in plan.configuration.inputs:
        source = (root / filepath).resolve()
        if not source.is_relative_to(root) or source.suffix.lower() != ".json":
            raise FunctionalWorkflowError(
                "Workflow inputs must be JSON files contained in project_root"
            )
        catalog.append(
            CatalogDataset(
                argument, "json.JSONDataset", f"data/01_raw/{argument}.json", str(source)
            )
        )
    functions = tuple(dict.fromkeys(step.function for step in plan.steps))
    return ConversionPlan(
        schema_version="1.0",
        planner_version="functional-workflow-1.0",
        notebook_path=plan.analysis.sources[0].path,
        task_candidates=tasks,
        imports=(f"from {package_name}.workflow_source import {', '.join(functions)}",),
        catalog_datasets=tuple(catalog),
        parameters=tuple(
            ParameterValue(name, value, name, "") for name, value in plan.configuration.parameters
        ),
    )


def generate_functional_kedro_project(  # noqa: PLR0913
    path: str | Path,
    configuration: FunctionalWorkflowConfiguration,
    output_path: str | Path,
    *,
    project_root: str | Path | None = None,
    package_name: str = "generated_workflow",
    architecture_profile: KedroArchitectureProfile | None = None,
    regression_contract: WorkflowRegressionContract | None = None,
) -> tuple[Path, ...]:
    """Recompute wiring and publish a new project; never execute source or a generated node."""
    root = Path.cwd() if project_root is None else Path(project_root).resolve()
    plan = plan_functional_workflow_path(path, configuration, project_root=root)
    files, copies = render_functional_workflow(
        plan,
        root=root,
        package_name=package_name,
        architecture_profile=architecture_profile,
        regression_contract=regression_contract,
    )
    return write_project(Path(output_path), files, copies)


def render_functional_workflow(
    plan: FunctionalWorkflowPlan,
    *,
    root: Path,
    package_name: str,
    architecture_profile: KedroArchitectureProfile | None = None,
    regression_contract: WorkflowRegressionContract | None = None,
) -> tuple[dict[Path, str], tuple[tuple[Path, Path], ...]]:
    """Render an internally recomputed workflow plan without publication or execution."""
    if plan_functional_workflow(plan.analysis, plan.configuration) != plan:
        raise FunctionalWorkflowError("Functional plan differs from recomputed source wiring")
    configuration = plan.configuration
    conversion = _conversion_plan(plan, root, package_name)
    # Always resolve generated wrapper names, including default-profile compatibility checks.
    profile = DEFAULT_KEDRO_PROFILE if architecture_profile is None else architecture_profile
    files, copies = render_kedro_project(
        conversion, package_name=package_name, architecture_profile=profile
    )
    combined = "\n\n".join(unit.source for unit in plan.analysis.sources)
    try:
        # Normalize encoding cookies/comments while preserving every original instruction AST.
        module_source = ast.unparse(ast.parse(combined)) + "\n"
        compile(module_source, "workflow_source.py", "exec", dont_inherit=True)
    except (SyntaxError, ValueError) as error:
        raise FunctionalWorkflowError(f"Cannot relocate workflow module: {error}") from error
    source_target = Path("src") / package_name / "workflow_source.py"
    files[source_target] = module_source
    catalog = {
        dataset.name: {"type": dataset.type, "filepath": dataset.filepath}
        for dataset in conversion.catalog_datasets
    }
    catalog.update(
        {
            name: {"type": "json.JSONDataset", "filepath": filepath}
            for name, filepath in configuration.outputs
        }
    )
    catalog.update(
        {step.output: {"type": "MemoryDataset", "copy_mode": "assign"} for step in plan.steps[:-1]}
    )
    files[Path("conf/base/catalog.yml")] = json.dumps(catalog, sort_keys=True, indent=2) + "\n"
    files[Path("conf/base/parameters.yml")] = (
        json.dumps(dict(configuration.parameters), sort_keys=True, indent=2) + "\n"
    )
    manifest = {
        **json.loads(plan.to_json()),
        "source_module": source_target.as_posix(),
        "statement_destinations": [
            {
                "statement_id": item.id,
                "destination": source_target.as_posix(),
                "ast_sha256": item.ast_sha256,
                "span": asdict(item.span),
            }
            for item in plan.analysis.statements
        ],
        "profile_sha256": profile.sha256,
    }
    files[Path("functional-workflow.json")] = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    files.update(render_workflow_regression_tests(plan, profile, package_name, regression_contract))
    if regression_contract is not None:
        files[Path("pyproject.toml")] += (
            '\n[project.optional-dependencies]\ntest = ["pytest>=9,<10"]\n'
            '\n[tool.pytest.ini_options]\npythonpath = ["src"]\ntestpaths = ["tests"]\n'
        )
    return files, copies
