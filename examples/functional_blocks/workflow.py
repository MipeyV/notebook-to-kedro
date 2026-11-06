"""Explicit functions used for static notebook/script structure comparison."""

import math


def prepare_values(values: float, scale: float) -> float:
    """Scale the supplied value."""
    prepared = values * scale
    return prepared


def summarize(values: float, scale: float) -> float:
    """Report the magnitude after scaling."""
    prepared = prepare_values(values, scale)
    total = math.fabs(prepared)
    return total
