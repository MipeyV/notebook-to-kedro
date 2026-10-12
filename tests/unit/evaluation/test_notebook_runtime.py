"""Local runtime identity collection and strict draft replay compatibility."""

from __future__ import annotations

import importlib.metadata
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro.evaluation import notebook_runtime as runtime

ROOT = Path(__file__).resolve().parents[3]


def test_collects_local_runtime_and_unknown_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def version(name: str) -> str:
        if name == "pandas":
            raise importlib.metadata.PackageNotFoundError(name)
        return "fixture-1"

    monkeypatch.setattr(importlib.metadata, "version", version)
    identity = runtime.collect_notebook_runtime_identity(tmp_path)
    assert identity.lock_sha256 is None
    assert dict(identity.packages)["pandas"] is None
    assert not identity.replayable
    assert len(identity.package_sha256) == 64
    assert identity.python_version
    assert identity.implementation
    assert identity.machine
    with pytest.raises(ValueError, match="known lock"):
        runtime.require_notebook_runtime_compatibility(identity, identity, identity)


def test_runtime_compatibility_and_code_or_lock_drift(tmp_path: Path) -> None:
    identity = runtime.collect_notebook_runtime_identity(ROOT)
    assert identity.replayable
    runtime.require_notebook_runtime_compatibility(identity, identity, identity)
    for field in (
        "python_version",
        "platform",
        "machine",
        "implementation",
        "lock_sha256",
        "package_sha256",
    ):
        value = "0" * 64 if field.endswith("sha256") else "changed"
        changes: dict[str, Any] = {field: value}
        changed = replace(identity, **changes)
        with pytest.raises(ValueError, match="mismatch"):
            runtime.require_notebook_runtime_compatibility(identity, changed, identity)
        with pytest.raises(ValueError, match="mismatch"):
            runtime.require_notebook_runtime_compatibility(identity, identity, changed)
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "one.py").write_text("one = 1\n", encoding="utf-8")
    initial = runtime._package_digest(sources)
    (sources / "one.py").write_text("one = 2\n", encoding="utf-8")
    assert runtime._package_digest(sources) != initial


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("python_version", "", "non-empty"),
        ("implementation", 1, "non-empty"),
        ("platform", " ", "non-empty"),
        ("machine", None, "non-empty"),
        ("packages", (), "inventory"),
        ("lock_sha256", "A" * 64, "SHA256"),
        ("package_sha256", True, "SHA256"),
        ("package_sha256", None, "required"),
    ],
)
def test_runtime_rejects_invalid_identities(field: str, value: Any, message: str) -> None:
    identity = runtime.collect_notebook_runtime_identity(ROOT)
    with pytest.raises(ValueError, match=message):
        replace(identity, **{field: value})


@pytest.mark.parametrize("value", ["", " ", 1])
def test_runtime_rejects_invalid_package_version(value: Any) -> None:
    identity = runtime.collect_notebook_runtime_identity(ROOT)
    packages = ((identity.packages[0][0], value), *identity.packages[1:])
    with pytest.raises(ValueError, match="versions"):
        replace(identity, packages=packages)


def test_runtime_file_and_aggregate_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "_MAX_IDENTITY_BYTES", 3)
    with pytest.raises(ValueError, match="unavailable"):
        runtime._package_digest(tmp_path)
    (tmp_path / "one.py").write_bytes(b"abcd")
    with pytest.raises(ValueError, match="file exceeds"):
        runtime._package_digest(tmp_path)
    (tmp_path / "one.py").write_bytes(b"ab")
    (tmp_path / "two.py").write_bytes(b"cd")
    with pytest.raises(ValueError, match="sources exceed"):
        runtime._package_digest(tmp_path)
