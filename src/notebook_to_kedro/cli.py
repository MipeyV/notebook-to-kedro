"""Command-line interface for Notebook to Kedro."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.api import (
    generate_kedro_project,
    plan_notebook_path,
    render_conversion_report,
    validate_conversion_plan,
)
from notebook_to_kedro.exceptions import (
    ConversionPlanValidationError,
    NotebookLoadError,
    PlannerConfigurationError,
    ProjectGenerationError,
)
from notebook_to_kedro.semantic import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    PlannerMode,
)

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan

ERROR_EXIT_CODE = 1


def main(argv: list[str] | None = None) -> int:
    """Run the Notebook to Kedro command-line interface."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            return _plan(args)
        if args.command == "generate":
            return _generate(args)
    except (
        ConversionPlanValidationError,
        NotebookLoadError,
        PlannerConfigurationError,
        ProjectGenerationError,
    ) as error:
        sys.stderr.write(f"Error: {error}\n")
        return ERROR_EXIT_CODE
    parser.error("missing command")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notebook-to-kedro",
        description="Analyze structured notebooks and render Kedro conversion plans.",
    )
    subparsers = parser.add_subparsers(dest="command")
    plan_parser = subparsers.add_parser(
        "plan",
        help="render a Markdown conversion report for a notebook",
    )
    plan_parser.add_argument("notebook", type=Path, help="path to the source notebook")
    plan_parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="root used to normalize notebook-relative paths",
    )
    _add_planner_arguments(plan_parser)
    generate_parser = subparsers.add_parser(
        "generate",
        help="generate a minimal Kedro project from a notebook",
    )
    generate_parser.add_argument("notebook", type=Path, help="path to the source notebook")
    generate_parser.add_argument("output_dir", type=Path, help="destination directory to create")
    generate_parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="root used to normalize notebook-relative paths",
    )
    generate_parser.add_argument(
        "--package-name",
        default="generated_notebook",
        help="Python package name for the generated Kedro project",
    )
    _add_planner_arguments(generate_parser)
    return parser


def _add_planner_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--planner",
        type=PlannerMode,
        choices=tuple(PlannerMode),
        default=PlannerMode.DETERMINISTIC,
        help="planning mode (default: deterministic)",
    )
    parser.add_argument(
        "--ollama-model",
        default=None,
        metavar="MODEL",
        help="downloaded local Ollama model required by the hybrid planner",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        metavar="URL",
        help="local Ollama server URL",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="Ollama request timeout in seconds",
    )


def _plan_from_args(args: argparse.Namespace) -> ConversionPlan:
    return plan_notebook_path(
        args.notebook,
        project_root=args.project_root,
        planner=args.planner,
        ollama_model=args.ollama_model,
        ollama_base_url=args.ollama_base_url,
        ollama_timeout_seconds=args.ollama_timeout,
    )


def _plan(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    sys.stdout.write(render_conversion_report(plan))
    return 0


def _generate(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    validate_conversion_plan(plan)
    created_files = generate_kedro_project(
        plan,
        args.output_dir,
        package_name=args.package_name,
    )
    sys.stdout.write(f"Created Kedro project at `{args.output_dir}`\n")
    for path in created_files:
        sys.stdout.write(f"- `{path}`\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
