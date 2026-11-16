"""Capture explicit source Git context, published-file identities and installed versions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.analysis.application_project import capture_application_project
from notebook_to_kedro.analysis.file_inputs import _regular_file, capture_file_references
from notebook_to_kedro.analysis.source_packages import capture_source_package
from notebook_to_kedro.exceptions import WorkflowProvenanceError
from notebook_to_kedro.generation.kedro.inventory import GENERATION_INVENTORY, file_identity
from notebook_to_kedro.generation.workflow_preparation import render_workflow_preparation
from notebook_to_kedro.generation.writer import validate_project_files, write_project
from notebook_to_kedro.semantic.functional_config import _unique_object
from notebook_to_kedro.semantic.workflow_preparation import (
    WorkflowCall,
    WorkflowPreparationDefinition,
)

if TYPE_CHECKING:
    from notebook_to_kedro.ir.application_project import ApplicationDistribution
    from notebook_to_kedro.ir.source_package import SourcePackage
    from notebook_to_kedro.semantic.functional_config import FunctionalWorkflowConfiguration

MAX_PROVENANCE_JSON_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_RUNTIME_PROBE = """import importlib.metadata, json, platform, sys
print(json.dumps({
    "python": platform.python_version(), "implementation": platform.python_implementation(),
    "executable": sys.executable,
    "distributions": sorted(
        ({"name": item.metadata["Name"], "version": item.version}
         for item in importlib.metadata.distributions()), key=lambda item: item["name"].lower()),
}))
"""


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    path = _regular_file(root, relative)
    with path.open("rb") as stream:
        content = stream.read(MAX_PROVENANCE_JSON_BYTES + 1)
    if len(content) > MAX_PROVENANCE_JSON_BYTES:
        raise WorkflowProvenanceError("Provenance JSON exceeds 16 MiB")
    value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise WorkflowProvenanceError("Provenance evidence must be a JSON object")
    return value


def _git_context(root: Path) -> dict[str, object]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root)]
    commit = subprocess.run(
        [*command, "rev-parse", "--verify", "HEAD"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    ).stdout.strip()
    if _GIT_SHA.fullmatch(commit) is None:
        raise WorkflowProvenanceError("Git returned an invalid source commit identity")
    status = subprocess.run(
        [
            *command,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=all",
        ],
        env=environment,
        capture_output=True,
        timeout=15,
        check=True,
    ).stdout
    return {
        "commit": commit,
        "working_tree": "dirty" if status else "clean",
        "untracked_policy": "normal",
        "submodule_policy": "ignored",
    }


def _runtime_metadata(python: Path, project: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(key, None)
    result = subprocess.run(
        [str(python.absolute()), "-I", "-c", _RUNTIME_PROBE],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload = json.loads(result.stdout)
    if (
        not isinstance(payload, dict)
        or payload.keys() != {"python", "implementation", "executable", "distributions"}
        or any(
            not isinstance(payload[key], str) or not payload[key]
            for key in ("python", "implementation", "executable")
        )
        or not isinstance(payload["distributions"], list)
        or any(
            not isinstance(item, dict)
            or item.keys() != {"name", "version"}
            or any(not isinstance(item[key], str) or not item[key] for key in ("name", "version"))
            for item in payload["distributions"]
        )
    ):
        raise WorkflowProvenanceError("Interpreter returned invalid distribution metadata")
    return payload


def _verified_inventory(project: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(project, GENERATION_INVENTORY.as_posix())
    entries = payload.get("files")
    if (
        payload.keys() != {"schema_version", "scope", "files"}
        or payload["schema_version"] != "1.0"
        or payload["scope"] != "published_files"
        or not isinstance(entries, dict)
        or not {"functional-workflow.json", "pyproject.toml"} <= entries.keys()
    ):
        raise WorkflowProvenanceError("Invalid generated-file inventory")
    validate_project_files({Path(path): "" for path in entries})
    for relative, expected in entries.items():
        if (
            not isinstance(expected, dict)
            or expected.keys() != {"sha256", "size_bytes", "kind"}
            or not isinstance(expected["sha256"], str)
            or _SHA256.fullmatch(expected["sha256"]) is None
            or type(expected["size_bytes"]) is not int
            or expected["size_bytes"] < 0
            or expected["kind"] not in ("generated", "copied")
        ):
            raise WorkflowProvenanceError("Invalid generated-file identity")
        actual = file_identity(_regular_file(project, relative))
        if actual != {"sha256": expected["sha256"], "size_bytes": expected["size_bytes"]}:
            raise WorkflowProvenanceError(
                f"Generated file differs from its published identity: {relative}"
            )
    return entries


def _require_copied(
    entries: dict[str, dict[str, Any]], target: Path, identity: dict[str, str | int]
) -> None:
    if entries.get(target.as_posix()) != {**identity, "kind": "copied"}:
        raise WorkflowProvenanceError(f"Generated copy differs from the selected source: {target}")


def _source_copies(
    root: Path,
    configuration: FunctionalWorkflowConfiguration,
    package: SourcePackage,
    application: ApplicationDistribution,
) -> dict[str, dict[str, str | int]]:
    target = Path("application") / application.package_root
    copies: dict[str, dict[str, str | int]] = {
        (target / item.path).as_posix(): {"sha256": item.sha256, "size_bytes": item.size_bytes}
        for item in package.files
    }
    copies.update(
        {
            (Path("application") / item.path).as_posix(): {
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in application.files
        }
    )
    for inventory in capture_file_references(root, configuration.file_inputs):
        for referenced in inventory.files:
            copies[
                (Path("data/01_raw") / inventory.argument / Path(referenced.path).name).as_posix()
            ] = {"sha256": referenced.sha256, "size_bytes": referenced.size_bytes}
    for name, relative in configuration.inputs:
        contained = (root / relative).resolve().relative_to(root).as_posix()
        copies[f"data/01_raw/{name}.json"] = file_identity(_regular_file(root, contained))
    return copies


def _preparation_definition(prepared: dict[str, Any]) -> WorkflowPreparationDefinition:
    definition = WorkflowPreparationDefinition.from_dict(prepared["definition"])
    steps = prepared["proposal"]["steps"]
    if not isinstance(steps, list) or len(steps) != len(definition.calls):
        raise WorkflowProvenanceError("Prepared call inventory differs from its definition")
    calls = []
    for call, step in zip(definition.calls, steps, strict=True):
        ordered = WorkflowCall(
            call.function, tuple(tuple(pair) for pair in step["inputs"]), call.output
        )
        if dict(ordered.arguments) != dict(call.arguments):
            raise WorkflowProvenanceError("Prepared argument bindings differ from their definition")
        calls.append(ordered)
    return replace(definition, calls=tuple(calls))


def _source_lineage(
    root: Path,
    project: Path,
    manifest: dict[str, Any],
    package: SourcePackage,
    application: ApplicationDistribution,
) -> str:
    if manifest["source_package_sha256"] == package.sha256:
        if (
            manifest["source_module"]
            != (Path("application") / application.package_root / package.source_file).as_posix()
        ):
            raise WorkflowProvenanceError(
                "Generated source module differs from the original selection"
            )
        return "original_package"
    prepared = _read_json(project, "application/workflow-preparation.json")
    expected, _ = render_workflow_preparation(
        root / package.root / package.source_file,
        _preparation_definition(prepared),
        project_root=root,
    )
    if (
        prepared != json.loads(expected[Path("workflow-preparation.json")])
        or prepared["source_package_sha256"] != package.sha256
    ):
        raise WorkflowProvenanceError(
            "Prepared orchestration differs from recomputed original source"
        )
    adapter = (Path("application") / prepared["proposal"]["adapter"]).as_posix()
    if (
        manifest["source_module"] != adapter
        or file_identity(_regular_file(project, adapter))["sha256"]
        != prepared["proposal"]["sha256"]
    ):
        raise WorkflowProvenanceError("Prepared adapter differs from its declared generation")
    return "recomputed_preparation_proposal"


def _installed_projects(
    runtime: dict[str, Any], application: ApplicationDistribution, project: Path
) -> list[dict[str, str]]:
    with _regular_file(project, "pyproject.toml").open("rb") as stream:
        generated = tomllib.load(stream)["project"]
    if not isinstance(generated, dict) or any(
        not isinstance(generated.get(key), str) or not generated[key] for key in ("name", "version")
    ):
        raise WorkflowProvenanceError("Generated project requires static distribution identity")
    projects = []
    for name, version in (
        (application.name, application.version),
        (generated["name"], generated["version"]),
    ):
        key = re.sub(r"[-_.]+", "-", name).lower()
        installed = [
            item["version"]
            for item in runtime["distributions"]
            if re.sub(r"[-_.]+", "-", item["name"]).lower() == key
        ]
        if len(installed) != 1:
            raise WorkflowProvenanceError(f"Interpreter requires one installed distribution {name}")
        projects.append(
            {"name": name, "declared_version": version, "installed_version": installed[0]}
        )
    return projects


def _execution_git_context(project: Path) -> dict[str, object]:
    try:
        return {"status": "observed", **_git_context(project)}
    except (OSError, subprocess.SubprocessError):
        return {"status": "unavailable"}


def capture_workflow_provenance(  # noqa: PLR0913
    source: str | Path,
    configuration: FunctionalWorkflowConfiguration,
    generated_project: str | Path,
    output_path: str | Path,
    *,
    project_root: str | Path,
    python_executable: str | Path,
) -> tuple[Path, ...]:
    """Bind original source, generated files and installed versions in a new report bundle."""
    if configuration.application_project is None or configuration.source_package is None:
        raise WorkflowProvenanceError(
            "Workflow provenance requires explicit application project configuration"
        )
    root, project, destination = (
        Path(project_root).resolve(),
        Path(generated_project).resolve(),
        Path(output_path).absolute(),
    )
    if any(
        destination.resolve().is_relative_to(value) or value.is_relative_to(destination.resolve())
        for value in (root / configuration.source_package, project)
    ):
        raise WorkflowProvenanceError(
            "Provenance destination overlaps the source or generated project"
        )
    try:
        source_git = _git_context(root)
        package = capture_source_package(root, Path(source), configuration.source_package)
        application = capture_application_project(
            root, configuration.application_project, package.root
        )
        copies = _source_copies(root, configuration, package, application)
        entries = _verified_inventory(project)
        manifest = _read_json(project, "functional-workflow.json")
        for target, identity in copies.items():
            _require_copied(entries, Path(target), identity)
        lineage = _source_lineage(root, project, manifest, package, application)
        runtime = _runtime_metadata(Path(python_executable), project)
        runtime = {
            **runtime,
            "selected_projects": _installed_projects(runtime, application, project),
        }
        execution_git = _execution_git_context(project)
        if (
            source_git != _git_context(root)
            or package != capture_source_package(root, Path(source), configuration.source_package)
            or application
            != capture_application_project(root, configuration.application_project, package.root)
            or copies != _source_copies(root, configuration, package, application)
            or entries != _verified_inventory(project)
        ):
            raise WorkflowProvenanceError(
                "Source or generated evidence changed during provenance capture"
            )
        payload = {
            "schema_version": "1.0",
            "status": "captured",
            "benchmark_execution": "not_run",
            "source": {
                "git": source_git,
                "module": package.source_file,
                "package_root": package.root,
                "distribution": {"name": application.name, "version": application.version},
                "package_sha256": package.sha256,
                "application_sha256": application.sha256,
                "lineage": lineage,
                "copies": copies,
            },
            "generation": {
                "inventory": file_identity(project / GENERATION_INVENTORY),
                "files": entries,
                "validation": "listed_files_match",
            },
            "environment": runtime,
            "execution_directory_git": execution_git,
            "review_status": "not_established",
        }
        return write_project(
            destination,
            {
                Path("workflow-provenance.json"): json.dumps(payload, sort_keys=True, indent=2)
                + "\n"
            },
        )
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        if isinstance(error, WorkflowProvenanceError):
            raise
        raise WorkflowProvenanceError(f"Cannot capture workflow provenance: {error}") from error
