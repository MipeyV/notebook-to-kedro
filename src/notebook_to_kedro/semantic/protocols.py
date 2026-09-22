"""Provider-neutral semantic planning contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts
    from notebook_to_kedro.semantic.providers import SemanticProviderRequest


class SemanticPlanner(Protocol):
    """Create a conversion plan from deterministic notebook facts."""

    def create_plan(self, facts: NotebookFacts) -> ConversionPlan:
        """Return a reviewable conversion plan for the supplied notebook facts."""
        ...


class SemanticPlanningProvider(Protocol):
    """Return raw structured output without owning planning validation."""

    provider_name: str
    model_name: str

    def complete(self, request: SemanticProviderRequest) -> str:
        """Return one raw JSON response for a provider request."""
        ...
