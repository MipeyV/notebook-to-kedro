"""Package metadata tests."""

from notebook_to_kedro import (
    __version__,
    analyze_notebook_path,
    generate_kedro_project,
    plan_notebook_path,
    render_conversion_report,
    validate_conversion_plan,
)


def test_package_exposes_version() -> None:
    """The initial package exposes its version through the public API."""
    assert __version__ == "0.1.0"


def test_package_exposes_public_analysis_api() -> None:
    """The package root exposes the notebook path analysis entrypoint."""
    assert analyze_notebook_path.__name__ == "analyze_notebook_path"
    assert callable(analyze_notebook_path)


def test_package_exposes_public_planning_api() -> None:
    """The package root exposes the notebook path planning entrypoint."""
    assert plan_notebook_path.__name__ == "plan_notebook_path"
    assert callable(plan_notebook_path)


def test_package_exposes_public_generation_api() -> None:
    """The package root exposes the Kedro generation entrypoint."""
    assert generate_kedro_project.__name__ == "generate_kedro_project"
    assert callable(generate_kedro_project)


def test_package_exposes_public_reporting_api() -> None:
    """The package root exposes the conversion report renderer."""
    assert render_conversion_report.__name__ == "render_conversion_report"
    assert callable(render_conversion_report)


def test_package_exposes_public_plan_validation_api() -> None:
    """The package root exposes the conversion plan validation entrypoint."""
    assert validate_conversion_plan.__name__ == "validate_conversion_plan"
    assert callable(validate_conversion_plan)
