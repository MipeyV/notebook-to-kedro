"""Explicit forwarding workflow with separately installed application metadata."""

from distribution_ml.domain import summarize


def report(raw: float, factor: float) -> dict:
    """Delegate to the application implementation."""
    return summarize(raw, factor)


def workflow(raw: float, factor: float) -> dict:
    """Expose one named result for Kedro wiring."""
    result = report(raw, factor)
    return result
