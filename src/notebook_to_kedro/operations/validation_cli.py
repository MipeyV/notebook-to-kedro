"""CLI adapters for the separately authorized generated-project execution operation."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import LocalOperationError
from notebook_to_kedro.operations.configuration import load_local_project_configuration
from notebook_to_kedro.operations.generated_validation import run_generated_validation
from notebook_to_kedro.operations.validation_snapshot import (
    GeneratedValidationRequest,
    prepare_generated_validation,
)

if TYPE_CHECKING:
    import argparse
    from types import FrameType


def add_validation_parsers(actions: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Keep execution controls separate from static inspect/plan/generate envelopes."""
    for name in ("validation-plan", "validate"):
        parser = actions.add_parser(name, help="review or explicitly run delivered notebook tests")
        parser.add_argument("configuration", type=Path)
        parser.add_argument("project", type=Path)
        parser.add_argument(
            "--python",
            type=Path,
            required=True,
            help="existing absolute project-runtime interpreter",
        )
        parser.add_argument(
            "--output", type=Path, required=True, help="new contained validation attempt directory"
        )
        parser.add_argument("--timeout", type=int, default=300, help="worker seconds, 1..600")
        if name == "validate":
            parser.add_argument(
                "--approved-sha256", required=True, help="reviewed validation-plan identity"
            )
            parser.add_argument(
                "--cancellable-stdin",
                action="store_true",
                help="cancel on stdin line/EOF for desktop clients",
            )


def _stdin_cancel(cancel: threading.Event) -> None:
    os.read(sys.stdin.fileno(), 1)
    cancel.set()


def validation_cli(args: argparse.Namespace) -> int:
    """Prepare without execution, or honor explicit digest approval and cancellation."""
    try:
        request = GeneratedValidationRequest(
            load_local_project_configuration(args.configuration),
            args.project,
            args.python,
            args.output,
            args.timeout,
        )
        if args.project_action == "validation-plan":
            payload = prepare_generated_validation(request).to_dict()
        else:
            cancel = threading.Event()

            def interrupt(_signum: int, _frame: FrameType | None) -> None:
                cancel.set()

            previous = signal.signal(signal.SIGINT, interrupt)
            if args.cancellable_stdin:
                threading.Thread(target=_stdin_cancel, args=(cancel,), daemon=True).start()
            try:
                payload = run_generated_validation(
                    request, approved_sha256=args.approved_sha256, cancel=cancel
                ).to_dict()
            finally:
                signal.signal(signal.SIGINT, previous)
    except OSError as error:
        raise LocalOperationError("GV001", f"Cannot prepare validation attempt: {error}") from error
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0 if args.project_action == "validation-plan" or payload["status"] == "passed" else 1
