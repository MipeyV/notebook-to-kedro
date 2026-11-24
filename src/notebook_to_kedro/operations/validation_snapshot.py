"""Read-only, source-bound review of a generated notebook test snapshot."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from notebook_to_kedro.exceptions import LocalOperationError
from notebook_to_kedro.operations.configuration import LocalProjectConfiguration, contained_path
from notebook_to_kedro.operations.contracts import PlanRequest
from notebook_to_kedro.operations.service import plan_project
from notebook_to_kedro.operations.validation_process import WORKER

MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_FILES = 4096
MAX_VALIDATION_SECONDS = 600


@dataclass(frozen=True, slots=True)
class GeneratedValidationRequest:
    """Explicit project, runtime, new attempt directory and bounded execution budget."""

    configuration: LocalProjectConfiguration
    project: Path
    python: Path
    output: Path
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        """Revalidate paths for API callers without launching the selected interpreter."""
        config = replace(self.configuration)
        if (
            type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= MAX_VALIDATION_SECONDS
        ):
            raise LocalOperationError(
                "GV001", "Validation timeout must be an integer in 1..600 seconds"
            )
        if (
            not isinstance(self.python, Path)
            or not self.python.is_absolute()
            or not self.python.is_file()
        ):
            raise LocalOperationError("GV001", "Choose an existing absolute Python executable")
        project = contained_path(config.project_root, self.project)
        output = contained_path(config.project_root, self.output)
        protected = [project, self.python.resolve(), config.source]
        protected.extend(
            path
            for path in (config.regression_contract, config.node_types, config.architecture_profile)
            if path is not None
        )
        if output.exists() or any(
            output == path or output in path.parents or path in output.parents for path in protected
        ):
            raise LocalOperationError(
                "GV001",
                "Validation output must be new and disjoint from project/runtime/source inputs",
            )
        if config.source_kind != "notebook" or config.regression_contract is None:
            raise LocalOperationError(
                "GV001",
                "Initial validation requires notebook settings with supplied regression tests",
            )
        if not project.is_dir():
            raise LocalOperationError("GV001", "Choose an existing generated project")
        object.__setattr__(self, "configuration", config)
        object.__setattr__(self, "project", project)
        object.__setattr__(self, "output", output)


def file_identity(path: Path, root: Path, remaining: int = MAX_SNAPSHOT_BYTES) -> tuple[str, int]:
    """Hash bounded regular contained files; reject symlinks/reparse points in every component."""
    if not path.is_relative_to(root):
        raise LocalOperationError("GV001", "Snapshot file escapes its declared root")
    item = path
    while True:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise LocalOperationError(
                "GV001", "Snapshot paths must not contain links/reparse points"
            )
        if item == root:
            break
        item = item.parent
    if not path.is_file() or path.stat().st_size > remaining:
        raise LocalOperationError("GV001", "Snapshot requires bounded regular files")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(min(1024 * 1024, remaining - size + 1)):
            size += len(block)
            if size > remaining:
                raise LocalOperationError("GV001", "Snapshot exceeds its byte budget")
            digest.update(block)
    return digest.hexdigest(), size


@dataclass(frozen=True, slots=True)
class GeneratedValidationPlan:
    """Review snapshot; its digest binds runtime choice, budget and exact copied inventory."""

    request: GeneratedValidationRequest
    files: tuple[tuple[str, str, int], ...]
    python_sha256: str
    inputs: tuple[tuple[str, str, int], ...]

    def details(self) -> dict[str, object]:
        """Describe intended side effects without claiming environment or test readiness."""
        request = self.request
        return {
            "schema_version": "1.0",
            "operation": "validation-plan",
            "execution_status": "not_run",
            "configuration": request.configuration.to_dict(),
            "project": str(request.project),
            "python": str(request.python),
            "python_sha256": self.python_sha256,
            "python_resolved": str(request.python.resolve()),
            "output": str(request.output),
            "timeout_seconds": request.timeout_seconds,
            "snapshot_scope": "current_renderer_inventory_only",
            "worker_sha256": hashlib.sha256(WORKER.encode("utf-8")).hexdigest(),
            "implementation": "generated-notebook-tests-v1",
            "python_flags": ["-I", "-B", "-X", "utf8", "-u"],
            "pytest_plugins": "autoload disabled",
            "pytest_capture": "disabled; output retained in bounded local log",
            "files": [
                {"path": name, "sha256": digest, "size": size} for name, digest, size in self.files
            ],
            "inputs": [
                {"path": name, "sha256": digest, "size": size} for name, digest, size in self.inputs
            ],
            "tests": ["tests/test_notebook_regressions.py"],
            "execution_notice": (
                "Tests execute project code, may train models and write files. "
                "The private copy is not a security sandbox."
            ),
            "installation": "none; use the selected existing environment",
        }

    @property
    def sha256(self) -> str:
        """Bind the complete deterministic review payload, excluding the digest itself."""
        return hashlib.sha256(
            json.dumps(self.details(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def to_dict(self) -> dict[str, object]:
        """Export a detached review payload and its approval identity."""
        return {**self.details(), "plan_sha256": self.sha256}


def prepare_generated_validation(request: GeneratedValidationRequest) -> GeneratedValidationPlan:
    """Recompute generation and verify selected project bytes, with no execution or writes."""
    request = replace(request)
    preview = plan_project(PlanRequest(request.configuration))
    expected = {file.path: file.sha256 for file in preview.files}
    expected.update({copy.destination: copy.sha256 for copy in preview.copies})
    if "tests/test_notebook_regressions.py" not in expected or len(expected) > MAX_SNAPSHOT_FILES:
        raise LocalOperationError(
            "GV001", "Validation needs a bounded delivered notebook test inventory"
        )
    files: list[tuple[str, str, int]] = []
    total = 0
    try:
        for name, expected_sha in sorted(expected.items()):
            digest, size = file_identity(
                request.project / name, request.project, MAX_SNAPSHOT_BYTES - total
            )
            if digest != expected_sha:
                raise LocalOperationError(
                    "GV002", f"Generated file differs from the current reviewed rendering: {name}"
                )
            files.append((name, digest, size))
            total += size
        resolved_python = request.python.resolve()
        python_sha, _ = file_identity(resolved_python, Path(resolved_python.anchor))
    except OSError as error:
        raise LocalOperationError("GV001", f"Cannot read validation inputs: {error}") from error
    inputs = {request.configuration.source}
    inputs.update(
        path
        for path in (
            request.configuration.regression_contract,
            request.configuration.node_types,
            request.configuration.architecture_profile,
        )
        if path is not None
    )
    inputs.update(request.configuration.project_root / copy.source for copy in preview.copies)
    captured = []
    for path in sorted(inputs):
        digest, size = file_identity(path, request.configuration.project_root)
        captured.append(
            (path.relative_to(request.configuration.project_root).as_posix(), digest, size)
        )
    return GeneratedValidationPlan(request, tuple(files), python_sha, tuple(captured))
