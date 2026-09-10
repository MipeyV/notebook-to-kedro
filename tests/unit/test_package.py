"""Package metadata tests."""

from notebook_to_kedro import __version__, analyze_notebook_path


def test_package_exposes_version() -> None:
    """The initial package exposes its version through the public API."""
    assert __version__ == "0.1.0"


def test_package_exposes_public_analysis_api() -> None:
    """The package root exposes the notebook path analysis entrypoint."""
    assert analyze_notebook_path.__name__ == "analyze_notebook_path"
    assert callable(analyze_notebook_path)
