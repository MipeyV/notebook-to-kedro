"""Render explicit destination checks around generated pipeline calls, never source functions."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import FunctionalWorkflowError

if TYPE_CHECKING:
    from notebook_to_kedro.generation.kedro.profiles import KedroArchitectureProfile
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan

MAX_ARTIFACT_POLICY_BYTES = 65536
_RUNTIME = '''"""Check declared bindings without sandboxing effects or reserving directories."""

import hashlib
import stat
from pathlib import Path

POLICY_SHA256 = {policy_sha256!r}
MAX_POLICY_BYTES = {max_policy_bytes}


def _directory_or_absent(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Artifact policy refuses links and reparse points")
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Artifact parent must be a directory")


def _project_root():
    root = Path.cwd().resolve()
    marker = root / "artifact-policy.json"
    info = marker.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Artifact policy marker must be a regular file")
    with marker.open("rb") as stream:
        content = stream.read(MAX_POLICY_BYTES + 1)
    if len(content) > MAX_POLICY_BYTES or hashlib.sha256(content).hexdigest() != POLICY_SHA256:
        raise ValueError("Artifact policy marker differs from the generated contract")
    return root


class ArtifactChecked:
    """Validate declared kwargs immediately before the owning generated node call."""

    def __init__(self, function, destinations):
        self.function = function
        self.destinations = destinations

    def __call__(self, **kwargs):
        root = _project_root()
        for parameter, key, expected in self.destinations:
            mapping = kwargs.get(parameter)
            if not isinstance(mapping, dict) or mapping.get(key) != expected:
                raise ValueError("Runtime artifact parameter differs from its declared path")
            # Paths are statically restricted to artifacts/<run_name>. Check without resolving
            # a target link, creating its parent, reserving it, retrying or deleting anything.
            parent = root / "artifacts"
            _directory_or_absent(parent)
            target = root / expected
            try:
                target.lstat()
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("Use a new application artifact destination: " + expected)
        return self.function(**kwargs)
'''


def render_artifact_policy(
    plan: FunctionalWorkflowPlan,
    profile: KedroArchitectureProfile,
    package_name: str,
    files: dict[Path, str],
) -> str | None:
    """Render explicit policy adapters without inspecting runtime destination paths."""
    bindings = plan.artifact_bindings()
    if not bindings:
        return None
    policy = (
        json.dumps({"schema_version": "1.0", "destinations": bindings}, sort_keys=True, indent=2)
        + "\n"
    )
    if len(policy.encode()) > MAX_ARTIFACT_POLICY_BYTES:
        raise FunctionalWorkflowError("Artifact policy exceeds 64 KiB")
    digest = hashlib.sha256(policy.encode()).hexdigest()
    runtime = _RUNTIME.format(policy_sha256=digest, max_policy_bytes=MAX_ARTIFACT_POLICY_BYTES)
    pipeline_path = Path("src") / package_name / "pipelines" / profile.pipeline_name / "pipeline.py"
    tree = ast.parse(files[pipeline_path])
    checks = {
        profile.node_name_prefix + step.name: tuple(
            (item["parameter"], item["key"], item["path"])
            for item in bindings
            if item["owner_step"] == step.id
        )
        for step in plan.steps
        if any(item["owner_step"] == step.id for item in bindings)
    }
    matched: list[str] = []
    for call in ast.walk(tree):
        if (
            not isinstance(call, ast.Call)
            or not isinstance(call.func, ast.Name)
            or call.func.id != "node"
        ):
            continue
        keywords = {item.arg: item for item in call.keywords}
        name = keywords.get("name")
        if (
            name is None
            or not isinstance(name.value, ast.Constant)
            or name.value.value not in checks
        ):
            continue
        label = cast("str", name.value.value)
        function = keywords.get("func")
        if function is None:
            raise FunctionalWorkflowError("Artifact owner node has no generated callable")
        function.value = ast.Call(
            ast.Name("_ArtifactChecked", ast.Load()),
            [function.value, ast.parse(repr(checks[label]), mode="eval").body],
            [],
        )
        matched.append(label)
    if sorted(matched) != sorted(checks):
        raise FunctionalWorkflowError(
            "Artifact owner bindings differ from generated pipeline nodes"
        )
    tree.body.insert(
        1,
        ast.ImportFrom(
            f"{package_name}._artifact_policy",
            [ast.alias("ArtifactChecked", "_ArtifactChecked")],
            0,
        ),
    )
    pipeline = ast.unparse(ast.fix_missing_locations(tree)) + "\n"
    compile(pipeline, pipeline_path.as_posix(), "exec", dont_inherit=True)
    compile(runtime, "_artifact_policy.py", "exec", dont_inherit=True)
    files[pipeline_path] = pipeline
    files[Path("src") / package_name / "_artifact_policy.py"] = runtime
    files[Path("artifact-policy.json")] = policy
    return digest
