"""Package metadata tests."""

from notebook_to_kedro import __version__


def test_package_exposes_version() -> None:
    """The initial package exposes its version through the public API."""
    assert __version__ == "0.1.0"
