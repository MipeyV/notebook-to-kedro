"""Load and validate Jupyter notebooks without analyzing Python code."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import nbformat
from nbformat import NotebookNode

from notebook_to_kedro.exceptions import NotebookLoadError
from notebook_to_kedro.notebook.models import LoadedCell, LoadedNotebook, NotebookCellKind

SUPPORTED_NBFORMAT = 4


def load_notebook(path: str | Path, *, project_root: str | Path | None = None) -> LoadedNotebook:
    """Load a supported Python notebook and preserve its cells in physical order."""
    notebook_path = Path(path)
    root_path = Path.cwd() if project_root is None else Path(project_root)
    notebook_bytes = _read_notebook_bytes(notebook_path)
    notebook = _read_notebook(notebook_path)
    _require_nbformat_4(notebook)
    language = _detect_python_language(notebook)
    kernel_name = _kernel_name(notebook)

    return LoadedNotebook(
        path=_portable_path(notebook_path, root_path),
        nbformat=_integer_field(notebook, "nbformat"),
        nbformat_minor=_integer_field(notebook, "nbformat_minor"),
        language=language,
        kernel_name=kernel_name,
        content_sha256=hashlib.sha256(notebook_bytes).hexdigest(),
        cells=_cells_from_notebook(notebook),
    )


def _read_notebook_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        message = f"Cannot read notebook: {path}"
        raise NotebookLoadError("NB001", message) from error


def _read_notebook(path: Path) -> NotebookNode:
    try:
        return cast(
            "NotebookNode",
            nbformat.read(path, as_version=nbformat.NO_CONVERT),  # type: ignore[no-untyped-call]
        )
    except Exception as error:
        message = f"Notebook cannot be loaded or validated: {path}"
        raise NotebookLoadError("NB001", message) from error


def _require_nbformat_4(notebook: NotebookNode) -> None:
    nbformat_major = _integer_field(notebook, "nbformat")
    if nbformat_major != SUPPORTED_NBFORMAT:
        message = f"Unsupported notebook format version: {nbformat_major}"
        raise NotebookLoadError("NB001", message)


def _detect_python_language(notebook: NotebookNode) -> str:
    metadata = _mapping_field(notebook, "metadata")
    language_info = _optional_mapping(metadata.get("language_info"))
    kernelspec = _optional_mapping(metadata.get("kernelspec"))
    candidates = (
        _optional_string(language_info.get("name") if language_info is not None else None),
        _optional_string(kernelspec.get("language") if kernelspec is not None else None),
    )
    language = next((candidate for candidate in candidates if candidate), None)
    if language is None or language.lower() != "python":
        message = "Notebook is not identified as Python."
        raise NotebookLoadError("NB002", message)
    return "python"


def _kernel_name(notebook: NotebookNode) -> str | None:
    metadata = _mapping_field(notebook, "metadata")
    kernelspec = _optional_mapping(metadata.get("kernelspec"))
    if kernelspec is None:
        return None
    return _optional_string(kernelspec.get("name"))


def _cells_from_notebook(notebook: NotebookNode) -> tuple[LoadedCell, ...]:
    cells = _sequence_field(notebook, "cells")
    return tuple(_cell_from_value(cell, index) for index, cell in enumerate(cells))


def _cell_from_value(value: object, index: int) -> LoadedCell:
    cell = _mapping(value, "cell")
    kind = _cell_kind(_required_string(cell, "cell_type"))
    return LoadedCell(
        id=f"cell-{index:04d}",
        index=index,
        kind=kind,
        source=_source_text(cell.get("source")),
        execution_count=_execution_count(cell, kind),
    )


def _cell_kind(value: str) -> NotebookCellKind:
    try:
        return NotebookCellKind(value)
    except ValueError as error:
        message = f"Unsupported notebook cell type: {value}"
        raise NotebookLoadError("NB001", message) from error


def _source_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "".join(value)
    message = "Notebook cell source must be a string or list of strings."
    raise NotebookLoadError("NB001", message)


def _execution_count(cell: dict[str, Any], kind: NotebookCellKind) -> int | None:
    if kind is not NotebookCellKind.CODE:
        return None
    value = cell.get("execution_count")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        message = "Code cell execution_count must be a non-negative integer or null."
        raise NotebookLoadError("NB001", message)
    return value


def _portable_path(path: Path, root_path: Path) -> str:
    try:
        return path.resolve().relative_to(root_path.resolve()).as_posix()
    except ValueError:
        return path.name


def _integer_field(payload: NotebookNode, field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        message = f"Notebook {field_name} must be an integer."
        raise NotebookLoadError("NB001", message)
    return value


def _mapping_field(payload: NotebookNode, field_name: str) -> dict[str, Any]:
    return _mapping(payload.get(field_name), field_name)


def _sequence_field(payload: NotebookNode, field_name: str) -> tuple[object, ...]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        message = f"Notebook {field_name} must be an array."
        raise NotebookLoadError("NB001", message)
    return tuple(value)


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        message = f"{field_name} must be an object."
        raise NotebookLoadError("NB001", message)
    if not all(isinstance(key, str) for key in value):
        message = f"{field_name} keys must be strings."
        raise NotebookLoadError("NB001", message)
    return cast("dict[str, Any]", value)


def _optional_mapping(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, "metadata field")


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        message = f"{field_name} must be a string."
        raise NotebookLoadError("NB001", message)
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Metadata string field must be a string."
        raise NotebookLoadError("NB001", message)
    return value
