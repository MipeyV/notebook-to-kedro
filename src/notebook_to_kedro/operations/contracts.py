"""Typed local requests and immutable review/publication results."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from notebook_to_kedro.ir import ConversionPlan
from notebook_to_kedro.operations.configuration import LocalProjectConfiguration, contained_path

if TYPE_CHECKING:
    from pathlib import Path

    from notebook_to_kedro.ir import NotebookFacts
    from notebook_to_kedro.ir.functional import FunctionalAnalysis
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan


@dataclass(frozen=True, slots=True)
class InspectRequest:
    """Inspect configured source without planning, writing or executing code."""

    configuration: LocalProjectConfiguration


@dataclass(frozen=True, slots=True)
class PlanRequest:
    """Recompute a plan and preview all rendered files without publication."""

    configuration: LocalProjectConfiguration


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    """Explicitly publish into a new destination contained in project_root."""

    configuration: LocalProjectConfiguration
    destination: Path

    def __post_init__(self) -> None:
        """Anchor a relative destination to the configured project root."""
        object.__setattr__(
            self, "destination", contained_path(self.configuration.project_root, self.destination)
        )


@dataclass(frozen=True, slots=True)
class FilePreview:
    """One complete new text file, with its exact UTF-8 content identity."""

    path: str
    content: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CopyPreview:
    """One input file to copy; its observed bytes are not an execution result."""

    source: str
    destination: str
    sha256: str


@dataclass(frozen=True, slots=True)
class InspectionResult:
    """Static source facts and their inspection-only status."""

    configuration: LocalProjectConfiguration
    analysis: NotebookFacts | FunctionalAnalysis
    status: Literal["inspected", "blocked"]

    def to_dict(self) -> dict[str, object]:
        """Export source facts without promoting inspection to conversion eligibility."""
        return {
            "schema_version": "1.0",
            "operation": "inspect",
            "status": self.status,
            "configuration": self.configuration.to_dict(),
            "analysis": json.loads(self.analysis.to_json()),
            "execution_status": "not_run",
        }


@dataclass(frozen=True, slots=True)
class PlanningResult:
    """A recomputed plan and the exact proposed new files; never a cached apply token."""

    configuration: LocalProjectConfiguration
    plan: ConversionPlan | FunctionalWorkflowPlan
    files: tuple[FilePreview, ...]
    copies: tuple[CopyPreview, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize a review snapshot, distinct from publication or runtime verification."""
        return {
            "schema_version": "1.0",
            "operation": "plan",
            "status": "planned",
            "configuration": self.configuration.to_dict(),
            "plan": asdict(self.plan)
            if isinstance(self.plan, ConversionPlan)
            else json.loads(self.plan.to_json()),
            "files": [asdict(item) for item in self.files],
            "copies": [asdict(item) for item in self.copies],
            "execution_status": "not_run",
        }


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Published paths; successful generation does not mean successful execution."""

    configuration: LocalProjectConfiguration
    destination: Path
    files: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Export publication evidence with explicit runtime/install gaps."""
        return {
            "schema_version": "1.0",
            "operation": "generate",
            "status": "generated",
            "configuration": self.configuration.to_dict(),
            "destination": self.destination.as_posix(),
            "files": list(self.files),
            "execution_status": "not_run",
            "installation_status": "not_checked",
        }
