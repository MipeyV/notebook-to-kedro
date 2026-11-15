"""Explicit workflow inside a declared local package."""

from example_ml.domain import Intermediate
from example_ml.transforms import finish_value, prepare_value


def prepare(values: float, scale: float) -> Intermediate:
    """Keep the package helper call and its original module globals."""
    return prepare_value(values, scale)


def summarize(prepared: Intermediate) -> dict:
    """Convert the synthetic internal value to its declared JSON result."""
    return finish_value(prepared)


def workflow(values: float, scale: float) -> dict:
    """Wire the package functions explicitly."""
    prepared = prepare(values, scale)
    total = summarize(prepared)
    return total
