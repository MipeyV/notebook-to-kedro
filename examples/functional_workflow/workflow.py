"""Linear workflow with internal calls retained inside their owning node."""

import math


def prepare_values(values: float, scale: float) -> float:
    """Scale a value exactly once."""
    prepared = values * scale
    return prepared


def summarize(prepared: float) -> float:
    """Report the magnitude of the prepared value."""
    total = math.fabs(prepared)
    return total


def workflow(values: float, scale: float) -> float:
    """Explicit ordered entrypoint used to derive the pipeline."""
    prepared = prepare_values(values, scale)
    total = summarize(prepared)
    return total
