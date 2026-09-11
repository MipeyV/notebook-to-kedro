"""Command-line interface for Notebook to Kedro."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from notebook_to_kedro.api import plan_notebook_path, render_conversion_report


def main(argv: list[str] | None = None) -> int:
    """Run the Notebook to Kedro command-line interface."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        return _plan(args)
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
    return parser


def _plan(args: argparse.Namespace) -> int:
    plan = plan_notebook_path(args.notebook, project_root=args.project_root)
    sys.stdout.write(render_conversion_report(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
