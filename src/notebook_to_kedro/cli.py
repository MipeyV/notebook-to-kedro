"""Command-line interface for Notebook to Kedro."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from notebook_to_kedro.api import (
    generate_kedro_project,
    plan_notebook_path,
    render_conversion_report,
)
from notebook_to_kedro.exceptions import NotebookLoadError, ProjectGenerationError

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
    except (NotebookLoadError, ProjectGenerationError) as error:
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
    return parser


def _plan(args: argparse.Namespace) -> int:
    plan = plan_notebook_path(args.notebook, project_root=args.project_root)
    sys.stdout.write(render_conversion_report(plan))
    return 0


def _generate(args: argparse.Namespace) -> int:
    plan = plan_notebook_path(args.notebook, project_root=args.project_root)
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
