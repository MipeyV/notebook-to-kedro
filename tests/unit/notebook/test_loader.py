"""Unit tests for the notebook loading boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from notebook_to_kedro.exceptions import NotebookLoadError
from notebook_to_kedro.notebook import (
    LoadedCell,
    LoadedNotebook,
    NotebookCellKind,
    load_notebook,
    loader,
)

if TYPE_CHECKING:
    from nbformat import NotebookNode


def _write_notebook(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _minimal_notebook(*, language: str = "python", nbformat: int = 4) -> dict[str, object]:
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "id": "heading",
                "metadata": {},
                "source": ["# Heading\n"],
            },
            {
                "cell_type": "code",
                "execution_count": 7,
                "id": "code",
                "metadata": {},
                "outputs": [],
                "source": ["value = 1\n", "value"],
            },
            {
                "cell_type": "raw",
                "id": "raw",
                "metadata": {},
                "source": "",
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": language, "name": "python3"},
            "language_info": {"name": language},
        },
        "nbformat": nbformat,
        "nbformat_minor": 5,
    }


def test_load_notebook_preserves_reference_fixture_cells() -> None:
    """The loader preserves notebook cells without analyzing their Python source."""
    path = Path("tests/fixtures/notebooks/simple_training.ipynb")

    notebook = load_notebook(path)

    assert notebook.path == "tests/fixtures/notebooks/simple_training.ipynb"
    assert notebook.nbformat == 4
    assert notebook.nbformat_minor == 5
    assert notebook.language == "python"
    assert notebook.kernel_name == "python3"
    assert notebook.cell_count == 12
    assert notebook.content_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert tuple(cell.index for cell in notebook.cells) == tuple(range(12))
    assert notebook.cells[0].kind is NotebookCellKind.MARKDOWN
    assert notebook.cells[1].kind is NotebookCellKind.CODE
    assert "from sklearn.datasets import load_iris" in notebook.cells[1].source
    assert all(cell.id == f"cell-{cell.index:04d}" for cell in notebook.cells)


def test_load_notebook_normalizes_source_lists(tmp_path: Path) -> None:
    """Jupyter list-form source fields are joined into plain strings."""
    path = tmp_path / "example.ipynb"
    _write_notebook(path, _minimal_notebook())

    notebook = load_notebook(path, project_root=tmp_path)

    assert notebook.path == "example.ipynb"
    assert notebook.cells[0].source == "# Heading\n"
    assert notebook.cells[1].source == "value = 1\nvalue"
    assert notebook.cells[1].execution_count == 7
    assert notebook.cells[2].kind is NotebookCellKind.RAW
    assert notebook.cells[2].execution_count is None


def test_load_notebook_accepts_kernelspec_python_language(tmp_path: Path) -> None:
    """A Python kernelspec is enough when language_info is absent."""
    path = tmp_path / "example.ipynb"
    payload = _minimal_notebook()
    metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}
    payload["metadata"] = metadata
    _write_notebook(path, payload)

    notebook = load_notebook(path, project_root=tmp_path)

    assert notebook.language == "python"
    assert notebook.kernel_name == "python3"


def test_load_notebook_accepts_missing_kernel_name(tmp_path: Path) -> None:
    """Kernel name is optional at the loading boundary."""
    path = tmp_path / "example.ipynb"
    payload = _minimal_notebook()
    payload["metadata"] = {"language_info": {"name": "python"}}
    _write_notebook(path, payload)

    notebook = load_notebook(path, project_root=tmp_path)

    assert notebook.kernel_name is None


@pytest.mark.parametrize(
    ("payload", "code", "message"),
    [
        (_minimal_notebook(language="r"), "NB002", "not identified as Python"),
        (_minimal_notebook(nbformat=3), "NB001", "loaded or validated"),
        ({"metadata": {}, "nbformat": 4, "nbformat_minor": 5}, "NB001", "loaded or validated"),
    ],
)
def test_load_notebook_rejects_unsupported_notebooks(
    tmp_path: Path,
    payload: dict[str, object],
    code: str,
    message: str,
) -> None:
    """Unsupported notebooks fail with stable MVP diagnostic codes."""
    path = tmp_path / "example.ipynb"
    _write_notebook(path, payload)

    with pytest.raises(NotebookLoadError, match=message) as error_info:
        load_notebook(path, project_root=tmp_path)

    assert error_info.value.code == code


def test_load_notebook_rejects_invalid_json(tmp_path: Path) -> None:
    """Malformed notebook JSON is reported as NB001."""
    path = tmp_path / "broken.ipynb"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(NotebookLoadError, match="loaded or validated") as error_info:
        load_notebook(path, project_root=tmp_path)

    assert error_info.value.code == "NB001"


def test_load_notebook_rejects_missing_file(tmp_path: Path) -> None:
    """Unreadable notebook paths are reported as NB001."""
    path = tmp_path / "missing.ipynb"

    with pytest.raises(NotebookLoadError, match="Cannot read notebook") as error_info:
        load_notebook(path, project_root=tmp_path)

    assert error_info.value.code == "NB001"


@pytest.mark.parametrize(
    ("cell", "message"),
    [
        (
            {"cell_type": "unsupported", "id": "unsupported", "metadata": {}, "source": ""},
            "Unsupported notebook cell",
        ),
        (
            {
                "cell_type": "code",
                "execution_count": -1,
                "id": "bad-count",
                "metadata": {},
                "outputs": [],
                "source": "",
            },
            "execution_count",
        ),
        (
            {
                "cell_type": "code",
                "execution_count": None,
                "id": "bad-source",
                "metadata": {},
                "outputs": [],
                "source": [1],
            },
            "loaded or validated",
        ),
    ],
)
def test_load_notebook_rejects_invalid_cells(
    tmp_path: Path, cell: dict[str, object], message: str
) -> None:
    """Invalid cell records fail before a source model is returned."""
    path = tmp_path / "example.ipynb"
    payload = _minimal_notebook()
    payload["cells"] = [cell]
    _write_notebook(path, payload)

    with pytest.raises(NotebookLoadError, match=message) as error_info:
        load_notebook(path, project_root=tmp_path)

    assert error_info.value.code == "NB001"


def test_loaded_cell_is_immutable() -> None:
    """Loaded notebook source models cannot be mutated after construction."""
    cell = LoadedCell("cell-0000", 0, NotebookCellKind.CODE, "value = 1")

    with pytest.raises(FrozenInstanceError):
        cell.index = 2  # type: ignore[misc]


def test_loader_reports_unsupported_nbformat_without_conversion() -> None:
    """The loader's version gate rejects non-v4 notebooks when reached."""
    notebook = cast("NotebookNode", {"nbformat": 3})

    with pytest.raises(NotebookLoadError, match="Unsupported notebook format") as error_info:
        loader._require_nbformat_4(notebook)

    assert error_info.value.code == "NB001"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (["valid", 1], "source"),
        (None, "source"),
    ],
)
def test_loader_rejects_invalid_cell_source_values(value: object, message: str) -> None:
    """Cell source values must normalize to a string."""
    with pytest.raises(NotebookLoadError, match=message):
        loader._source_text(value)


def test_loader_normalizes_valid_cell_source_list_directly() -> None:
    """The source normalizer joins a valid list of source fragments."""
    assert loader._source_text(["value = 1\n", "value"]) == "value = 1\nvalue"


def test_loader_uses_file_name_for_paths_outside_project_root(tmp_path: Path) -> None:
    """Portable paths fall back to the file name outside the selected project root."""
    notebook_path = tmp_path / "outside.ipynb"
    project_root = tmp_path / "project"

    assert loader._portable_path(notebook_path, project_root) == "outside.ipynb"


@pytest.mark.parametrize(
    ("payload", "field_name", "message"),
    [
        ({"nbformat": True}, "nbformat", "integer"),
        ({"nbformat": "4"}, "nbformat", "integer"),
    ],
)
def test_loader_rejects_invalid_integer_fields(
    payload: dict[str, object], field_name: str, message: str
) -> None:
    """Notebook integer fields reject booleans and strings."""
    with pytest.raises(NotebookLoadError, match=message):
        loader._integer_field(cast("NotebookNode", payload), field_name)


def test_loader_rejects_invalid_cells_field() -> None:
    """The notebook cells field must be an array."""
    with pytest.raises(NotebookLoadError, match="array"):
        loader._sequence_field(cast("NotebookNode", {"cells": "not-list"}), "cells")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "object"),
        ({1: "value"}, "keys"),
    ],
)
def test_loader_rejects_invalid_mapping_values(value: object, message: str) -> None:
    """Mapping helpers reject absent objects and non-string keys."""
    with pytest.raises(NotebookLoadError, match=message):
        loader._mapping(value, "metadata")


def test_loader_rejects_missing_required_string() -> None:
    """Required string fields must be present and strings."""
    with pytest.raises(NotebookLoadError, match="cell_type"):
        loader._required_string({}, "cell_type")


def test_loader_rejects_invalid_optional_string() -> None:
    """Optional metadata strings reject non-string values."""
    with pytest.raises(NotebookLoadError, match="Metadata string"):
        loader._optional_string(1)


def test_loader_rejects_invalid_execution_count_type() -> None:
    """Code cell execution counts reject booleans even though bool is an int subclass."""
    cell: dict[str, Any] = {"execution_count": True}

    with pytest.raises(NotebookLoadError, match="execution_count"):
        loader._execution_count(cell, NotebookCellKind.CODE)


@pytest.mark.parametrize(
    ("args", "kwargs", "message"),
    [
        (("", 0, NotebookCellKind.CODE, ""), {}, "cell id"),
        (("cell-0000", -1, NotebookCellKind.CODE, ""), {}, "cell index"),
        (
            ("cell-0000", 0, NotebookCellKind.CODE, ""),
            {"execution_count": -1},
            "execution_count",
        ),
        (
            ("cell-0000", 0, NotebookCellKind.MARKDOWN, ""),
            {"execution_count": 1},
            "only code cells",
        ),
    ],
)
def test_loaded_cell_rejects_invalid_values(
    args: tuple[object, ...], kwargs: dict[str, object], message: str
) -> None:
    """Loaded cells validate source-order identity and execution metadata."""
    with pytest.raises(ValueError, match=message):
        LoadedCell(*args, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"path": ""}, "path"),
        ({"path": "tests\\example.ipynb"}, "POSIX"),
        ({"language": ""}, "language"),
        ({"nbformat": 0}, "format versions"),
        ({"nbformat_minor": -1}, "format versions"),
        (
            {"cells": (LoadedCell("cell-0001", 1, NotebookCellKind.CODE, ""),)},
            "contiguously",
        ),
    ],
)
def test_loaded_notebook_rejects_invalid_values(overrides: dict[str, object], message: str) -> None:
    """Loaded notebooks validate portable metadata and physical cell order."""
    values = {
        "path": "tests/example.ipynb",
        "nbformat": 4,
        "nbformat_minor": 5,
        "language": "python",
        "kernel_name": "python3",
        "content_sha256": "a" * 64,
        "cells": (),
    } | overrides

    with pytest.raises(ValueError, match=message):
        LoadedNotebook(**values)  # type: ignore[arg-type]
