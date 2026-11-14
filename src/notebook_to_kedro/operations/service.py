"""Compose the existing deterministic engine for local callers; no UI transformation rules."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING

from notebook_to_kedro.analysis.functional_sources import analyze_functional_blocks_path
from notebook_to_kedro.api import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.exceptions import (
    ConversionPlanValidationError,
    FunctionalSourceError,
    LocalOperationError,
    NotebookLoadError,
    ProjectGenerationError,
)
from notebook_to_kedro.generation.kedro.functional import (
    plan_functional_workflow_path,
    render_functional_workflow,
)
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.generation.kedro.profiles import load_kedro_profile
from notebook_to_kedro.generation.kedro.regression_contract import load_workflow_regression_contract
from notebook_to_kedro.generation.writer import validate_project_files, write_project
from notebook_to_kedro.operations.configuration import LocalProjectConfiguration, contained_path
from notebook_to_kedro.operations.contracts import (
    CopyPreview,
    FilePreview,
    GenerateRequest,
    GenerationResult,
    InspectionResult,
    InspectRequest,
    PlanningResult,
    PlanRequest,
)
from notebook_to_kedro.semantic.functional_config import load_functional_workflow_configuration

if TYPE_CHECKING:
    from pathlib import Path

    from notebook_to_kedro.ir import ConversionPlan
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan


def inspect_project(request: InspectRequest) -> InspectionResult:
    """Inspect current source; never import application code or validate an execution claim."""
    config = replace(request.configuration)
    if config.source_kind == "notebook":
        facts = analyze_notebook_path(config.source, project_root=config.project_root)
        blocked = any(item.severity == "error" for item in facts.diagnostics)
        return InspectionResult(config, facts, "blocked" if blocked else "inspected")
    analysis = analyze_functional_blocks_path(config.source, project_root=config.project_root)
    return InspectionResult(config, analysis, "inspected" if analysis.complete else "blocked")


def _prepare(
    config: LocalProjectConfiguration,
) -> tuple[ConversionPlan | FunctionalWorkflowPlan, dict[Path, str], tuple[tuple[Path, Path], ...]]:
    config = replace(config)
    profile = (
        None
        if config.architecture_profile is None
        else load_kedro_profile(config.architecture_profile)
    )
    plan: ConversionPlan | FunctionalWorkflowPlan
    if config.source_kind == "notebook":
        plan = plan_notebook_path(config.source, project_root=config.project_root)
        files, copies = render_kedro_project(
            plan, package_name=config.package_name, architecture_profile=profile
        )
    else:
        assert config.workflow_configuration is not None
        plan = plan_functional_workflow_path(
            config.source,
            load_functional_workflow_configuration(config.workflow_configuration),
            project_root=config.project_root,
        )
        files, copies = render_functional_workflow(
            plan,
            root=config.project_root,
            package_name=config.package_name,
            architecture_profile=profile,
            regression_contract=None
            if config.regression_contract is None
            else load_workflow_regression_contract(config.regression_contract),
        )
    copies = tuple(
        (contained_path(config.project_root, source), target) for source, target in copies
    )
    validate_project_files(files, copies)
    return plan, files, copies


def plan_project(request: PlanRequest) -> PlanningResult:
    """Preview real renderer output and copied input identities, without creating a destination."""
    plan, files, copies = _prepare(request.configuration)
    previews = tuple(
        FilePreview(path.as_posix(), content, hashlib.sha256(content.encode("utf-8")).hexdigest())
        for path, content in sorted(files.items())
    )
    inputs: list[CopyPreview] = []
    for source, target in copies:
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inputs.append(
            CopyPreview(
                source.relative_to(request.configuration.project_root).as_posix(),
                target.as_posix(),
                digest,
            )
        )
    return PlanningResult(request.configuration, plan, previews, tuple(inputs))


def generate_project(request: GenerateRequest) -> GenerationResult:
    """Recompute from current inputs, then use the existing no-overwrite staging writer."""
    destination = contained_path(request.configuration.project_root, request.destination)
    _, files, copies = _prepare(request.configuration)
    created = write_project(destination, files, copies)
    return GenerationResult(
        request.configuration,
        destination,
        tuple(path.relative_to(destination).as_posix() for path in created),
    )


def run_local_operation(
    request: InspectRequest | PlanRequest | GenerateRequest,
) -> InspectionResult | PlanningResult | GenerationResult:
    """Dispatch a typed request; expected engine/I/O failures retain their original diagnostics."""
    try:
        if isinstance(request, InspectRequest):
            return inspect_project(request)
        if isinstance(request, PlanRequest):
            return plan_project(request)
        if isinstance(request, GenerateRequest):
            return generate_project(request)
        raise LocalOperationError("LO001", "Unsupported local operation request")
    except (
        OSError,
        ConversionPlanValidationError,
        FunctionalSourceError,
        NotebookLoadError,
        ProjectGenerationError,
    ) as error:
        raise LocalOperationError("LO002", str(error)) from error
