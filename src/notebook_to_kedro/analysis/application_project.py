"""Capture PEP 621 declarations and build inputs through static file reads."""

from __future__ import annotations

import hashlib
import re
import tomllib
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.analysis.file_inputs import capture_file_references
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.ir.application_project import ApplicationDistribution
from notebook_to_kedro.semantic.file_inputs import FileReferenceInput

if TYPE_CHECKING:
    from pathlib import Path

    from notebook_to_kedro.semantic.application_project import ApplicationProject

MAX_PROJECT_BYTES = 65536
_SPACE_CODEPOINT = 32


def _text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not any(ord(character) < _SPACE_CODEPOINT for character in value)
    )


def _requirements(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not _text(item) for item in value):
        raise FunctionalWorkflowError("Application dependency declarations must be string lists")
    return tuple(value)


def _mapping(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or any(
        not _text(key) or not _text(item) for key, item in value.items()
    ):
        raise FunctionalWorkflowError("Application script declarations must map names to strings")
    return tuple(sorted(value.items()))


def _metadata(data: dict[str, Any]) -> dict[str, Any]:
    project = data.get("project")
    if not isinstance(project, dict):
        raise FunctionalWorkflowError("Application pyproject requires a project table")
    if (
        not _text(project.get("name"))
        or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", project["name"]) is None
    ):
        raise FunctionalWorkflowError("Application project requires a distribution name")
    if (
        not _text(project.get("version"))
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", project["version"]) is None
    ):
        raise FunctionalWorkflowError("Application project requires a static version declaration")
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list) or any(
        item in dynamic for item in ("version", "dependencies", "optional-dependencies")
    ):
        raise FunctionalWorkflowError(
            "Application capture requires static version and dependency declarations"
        )
    if "requires-python" in project and not _text(project["requires-python"]):
        raise FunctionalWorkflowError("Application requires-python must be a string declaration")
    return project


def _referenced_files(project: dict[str, Any]) -> tuple[str, ...]:
    files: list[str] = []
    for key in ("readme", "license"):
        value = project.get(key)
        if key == "readme" and isinstance(value, str):
            files.append(value)
        elif isinstance(value, dict) and "file" in value:
            files.append(value["file"])
    return tuple(files)


def capture_application_project(
    root: Path,
    definition: ApplicationProject,
    source_package: str,
) -> ApplicationDistribution:
    """Read declarations and selected regular files without importing the application/backend."""
    root = root.resolve()
    metadata_path = root / definition.pyproject
    directory = metadata_path.parent
    package_path = root / source_package
    if not package_path.is_relative_to(directory) or package_path == directory:
        raise FunctionalWorkflowError(
            "Application source package must be inside the pyproject directory"
        )
    identity = capture_file_references(
        root, (("pyproject", FileReferenceInput(definition.pyproject)),)
    )[0].files[0]
    try:
        with metadata_path.open("rb") as stream:
            content = stream.read(MAX_PROJECT_BYTES + 1)
        if len(content) > MAX_PROJECT_BYTES:
            raise FunctionalWorkflowError("Application pyproject exceeds 64 KiB")
        if hashlib.sha256(content).hexdigest() != identity.sha256:
            raise FunctionalWorkflowError("Application metadata changed during capture")
        project = _metadata(tomllib.loads(content.decode("utf-8")))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise FunctionalWorkflowError(
            f"Cannot read application project metadata: {error}"
        ) from error
    dependencies = _requirements(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise FunctionalWorkflowError("Application optional dependencies must be a table")
    extras = tuple((name, _requirements(value)) for name, value in sorted(optional.items()))
    paths = tuple(dict.fromkeys(("pyproject.toml", *_referenced_files(project), *definition.files)))
    inventories = capture_file_references(
        directory,
        tuple((f"file_{index}", FileReferenceInput(path)) for index, path in enumerate(paths)),
    )
    files = tuple(item.files[0] for item in inventories)
    if files[0].sha256 != identity.sha256:
        raise FunctionalWorkflowError("Application metadata changed during capture")
    return ApplicationDistribution(
        definition.pyproject,
        package_path.relative_to(directory).as_posix(),
        project["name"],
        project["version"],
        project.get("requires-python"),
        dependencies,
        extras,
        _mapping(project.get("scripts", {})),
        tuple(sorted(project)),
        files,
    )
