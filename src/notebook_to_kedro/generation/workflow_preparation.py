"""Prepare a reviewable orchestration module alongside an unchanged source-package copy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.analysis.functional_sources import analyze_functional_blocks_path
from notebook_to_kedro.analysis.source_packages import capture_source_package
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.generation.writer import validate_project_files, write_project
from notebook_to_kedro.ir.functional import SourceUnit
from notebook_to_kedro.semantic.functional_workflow import plan_functional_steps

if TYPE_CHECKING:
    from notebook_to_kedro.ir.functional import FunctionalAnalysis
    from notebook_to_kedro.semantic.workflow_preparation import WorkflowPreparationDefinition

ADAPTER_FILENAME = "workflow_adapter.py"
_REVIEW = """# Prepared orchestration: review required

This directory is a source-package copy plus a newly proposed workflow_adapter.py.
Original package files retain their bytes. workflow-preparation.json separates observed
source facts from declared calls and synthesized adapter facts. No application code was run.

Review the proposed call order and forwarding functions before adopting the adapter.
Supporting modules are opaque source. An accepted static shape does not verify effects,
dependency installation, scientific intent or execution approval.

Persistent input/output types, paths, sidecars, runtime artifact destinations and regression
oracles are not defined by this preparation. Supply those contracts separately before Kedro
generation. No workflow I/O configuration, catalog, dependencies or pytest stubs are invented.
All declared arguments are conservatively single-use at this stage. Source-only inspection
and faithful conversion remain independently available.
"""


def _adapter_source(
    definition: WorkflowPreparationDefinition,
    observed: FunctionalAnalysis,
    module: str,
) -> str:
    functions = {block.name: block for block in observed.blocks}
    names = tuple(dict.fromkeys(call.function for call in definition.calls))
    if definition.entrypoint in functions:
        raise FunctionalWorkflowError(
            "Preparation entrypoint collides with an existing source function"
        )
    lines = ['"""Proposed orchestration; review call order and I/O before adoption."""', ""]
    for name in names:
        if name not in functions:
            raise FunctionalWorkflowError(f"Declared call has no observed source function: {name}")
        lines.append(f"from {module} import {name} as _original_{name}")
    for name in names:
        parameters = functions[name].parameters
        signature = ", ".join(parameters)
        arguments = ", ".join(f"{value}={value}" for value in parameters)
        lines.extend(
            ["", "", f"def {name}({signature}):", f"    return _original_{name}({arguments})"]
        )
    lines.extend(["", "", f"def {definition.entrypoint}({', '.join(definition.arguments)}):"])
    for call in definition.calls:
        arguments = ", ".join(f"{key}={value}" for key, value in call.arguments)
        lines.append(f"    {call.output} = {call.function}({arguments})")
    lines.append(f"    return {definition.output}")
    return "\n".join(lines) + "\n"


def render_workflow_preparation(
    source: str | Path,
    definition: WorkflowPreparationDefinition,
    *,
    project_root: str | Path | None = None,
) -> tuple[dict[Path, str], tuple[tuple[Path, Path], ...]]:
    """Preview new source and a manifest; never write, import or execute application code."""
    root = Path.cwd() if project_root is None else Path(project_root).resolve()
    package = capture_source_package(root, Path(source), definition.source_package)
    observed = analyze_functional_blocks_path(source, project_root=root)
    observed = analyze_functional_blocks(observed.sources, package_module=package.module)
    if not observed.complete:
        raise FunctionalWorkflowError("Preparation requires complete selected-module inspection")
    if observed.sources[0].document_sha256 != next(
        item.sha256 for item in package.files if item.path == package.source_file
    ):
        raise FunctionalWorkflowError("Preparation source differs from the captured package")
    target = Path("src") / package.name / ADAPTER_FILENAME
    code = _adapter_source(definition, observed, package.module)
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    proposed = analyze_functional_blocks(
        (SourceUnit("prepared_module", target.as_posix(), "python", digest, code),),
        package_module=f"{package.name}.workflow_adapter",
    )
    if not proposed.complete:
        raise FunctionalWorkflowError("Proposed orchestration fails functional inspection")
    functions = {block.name: block for block in proposed.blocks}
    entry = functions[definition.entrypoint]
    steps = plan_functional_steps(entry, functions, reusable_parameters=set(), source_order=True)
    manifest = {
        "schema_version": "1.0",
        "status": "unreviewed_proposal",
        "execution_status": "not_run",
        "persistent_io_status": "not_defined",
        "artifact_policy_status": "not_defined",
        "definition": definition.to_dict(),
        "source_facts": json.loads(observed.to_json()),
        "source_package": package.to_dict(),
        "source_package_sha256": package.sha256,
        "proposal": {
            "adapter": target.as_posix(),
            "sha256": digest,
            "analysis": json.loads(proposed.to_json()),
            "steps": [asdict(step) for step in steps],
            "ordering_policy": "source_order",
            "argument_policy": "single_use",
            "source_bindings": [
                {
                    "wrapper": name,
                    "module": package.module,
                    "function": name,
                    "source_block_id": block.id,
                    "source_ast_sha256": block.ast_sha256,
                }
                for name in dict.fromkeys(call.function for call in definition.calls)
                for block in observed.blocks
                if block.name == name
            ],
        },
    }
    files = {
        target: code,
        Path("workflow-preparation.json"): json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        Path("REVIEW.md"): _REVIEW,
    }
    copies = tuple(
        (root / package.root / item.path, Path("src") / package.name / item.path)
        for item in package.files
    )
    if capture_source_package(root, Path(source), definition.source_package) != package:
        raise FunctionalWorkflowError("Preparation package differs from the captured inventory")
    validate_project_files(files, copies)
    return files, copies


def prepare_functional_workflow(
    source: str | Path,
    definition: WorkflowPreparationDefinition,
    output_path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> tuple[Path, ...]:
    """Publish a new review copy; refuse writes inside the source package and any overwrite."""
    root = Path.cwd() if project_root is None else Path(project_root).resolve()
    package_path = (root / definition.source_package).resolve()
    destination = Path(output_path).resolve()
    if destination.is_relative_to(package_path) or package_path.is_relative_to(destination):
        raise FunctionalWorkflowError(
            "Preparation destination overlaps the original source package"
        )
    files, copies = render_workflow_preparation(source, definition, project_root=root)
    return write_project(destination, files, copies)
