"""Normalized notebook source models."""

from dataclasses import dataclass
from enum import StrEnum


class NotebookCellKind(StrEnum):
    """Notebook cell kinds preserved by the loader."""

    CODE = "code"
    MARKDOWN = "markdown"
    RAW = "raw"


@dataclass(frozen=True, slots=True)
class LoadedCell:
    """One notebook cell preserved in physical source order."""

    id: str
    index: int
    kind: NotebookCellKind
    source: str
    execution_count: int | None = None

    def __post_init__(self) -> None:
        if not self.id:
            message = "cell id must not be empty"
            raise ValueError(message)
        if self.index < 0:
            message = "cell index must be greater than or equal to zero"
            raise ValueError(message)
        if self.execution_count is not None and self.execution_count < 0:
            message = "execution_count must be greater than or equal to zero"
            raise ValueError(message)
        if self.kind is not NotebookCellKind.CODE and self.execution_count is not None:
            message = "only code cells may have an execution count"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class LoadedNotebook:
    """Notebook content normalized before semantic or AST analysis."""

    path: str
    nbformat: int
    nbformat_minor: int
    language: str
    kernel_name: str | None
    content_sha256: str
    cells: tuple[LoadedCell, ...]

    @property
    def cell_count(self) -> int:
        """Return the number of preserved cells."""
        return len(self.cells)

    def __post_init__(self) -> None:
        if not self.path:
            message = "path must not be empty"
            raise ValueError(message)
        if "\\" in self.path:
            message = "path must use POSIX separators"
            raise ValueError(message)
        if not self.language:
            message = "language must not be empty"
            raise ValueError(message)
        if self.nbformat < 1 or self.nbformat_minor < 0:
            message = "notebook format versions must be valid"
            raise ValueError(message)
        expected_indexes = tuple(range(len(self.cells)))
        actual_indexes = tuple(cell.index for cell in self.cells)
        if actual_indexes != expected_indexes:
            message = "cells must be ordered and indexed contiguously from zero"
            raise ValueError(message)
