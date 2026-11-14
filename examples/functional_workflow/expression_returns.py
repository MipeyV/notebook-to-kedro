"""Explicit workflow whose helpers return expressions without temporary variables."""

import math


def prepare_values(values: float, scale: float) -> float:
    """Scale a value directly in the return expression."""
    return values * scale


def summarize(prepared: float) -> float:
    """Return the magnitude with one library call."""
    return math.fabs(prepared)


def workflow(values: float, scale: float) -> float:
    """Retain explicit named orchestration boundaries."""
    prepared = prepare_values(values, scale)
    total = summarize(prepared)
    return total
