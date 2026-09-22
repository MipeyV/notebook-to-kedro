"""Provider-neutral semantic planning contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts


class SemanticPlanner(Protocol):
    """Create a conversion plan from deterministic notebook facts."""

    def create_plan(self, facts: NotebookFacts) -> ConversionPlan:
        """Return a reviewable conversion plan for the supplied notebook facts."""
        ...
