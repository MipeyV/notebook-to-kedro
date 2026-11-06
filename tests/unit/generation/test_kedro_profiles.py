"""Profile identity, strict configuration and incompatible naming contracts."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from notebook_to_kedro import DEFAULT_KEDRO_PROFILE, KedroArchitectureProfile, load_kedro_profile
from notebook_to_kedro.exceptions import KedroProfileError
from notebook_to_kedro.generation.kedro.profiles import MAX_PROFILE_BYTES, resolve_node_names
from notebook_to_kedro.ir import ConversionPlan, TaskCandidate

EXAMPLE = Path(__file__).parents[3] / "examples/kedro_profiles/team_training.json"


def _plan() -> ConversionPlan:
    return ConversionPlan(
        "1.0",
        "0.1.0",
        "notebooks/example.ipynb",
        (TaskCandidate("t1", "prepare", ("c1",), ("s1",), (), ("value",), "value = 1"),),
    )


def test_profile_roundtrip_defaults_and_configuration_identity() -> None:
    default = DEFAULT_KEDRO_PROFILE
    assert KedroArchitectureProfile.from_dict(json.loads(default.to_json())) == default
    minimal = {
        key: value
        for key, value in default.to_dict().items()
        if key in {"schema_version", "profile_id", "profile_version"}
    }
    assert KedroArchitectureProfile.from_dict(minimal) == default
    assert default.sha256 == KedroArchitectureProfile.from_dict(minimal).sha256
    assert replace(default, pipeline_name="training").sha256 != default.sha256
    assert json.loads(default.to_json())["node_name_prefix"] == ""


def test_checked_in_profile_is_reusable_without_changing_source_facts() -> None:
    profile = load_kedro_profile(EXAMPLE)
    plan = _plan()
    assert profile == KedroArchitectureProfile("example.team-training", "1.0.0", "training", "ml_")
    assert resolve_node_names(plan, profile) == {"t1": "ml_prepare"}
    assert plan == _plan()
    assert resolve_node_names(replace(plan, task_candidates=()), profile) == {}


@pytest.mark.parametrize(
    "field",
    ["schema_version", "profile_id", "profile_version", "pipeline_name", "node_name_prefix"],
)
@pytest.mark.parametrize("value", [None, 1, True, []])
def test_profile_rejects_nonstring_fields(field: str, value: object) -> None:
    data: dict[str, object] = dict(DEFAULT_KEDRO_PROFILE.to_dict())
    data[field] = value
    with pytest.raises(KedroProfileError, match="must be strings"):
        KedroArchitectureProfile.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "2.0", "Unsupported"),
        ("profile_id", "../unsafe", "profile_id"),
        ("profile_version", "latest", "profile_version"),
        ("pipeline_name", "../training", "pipeline_name"),
        ("pipeline_name", "class", "pipeline_name"),
        ("pipeline_name", "Training", "pipeline_name"),
        ("pipeline_name", "__default__", "pipeline_name"),
        ("pipeline_name", "nul", "pipeline_name"),
        ("node_name_prefix", "ml", "node_name_prefix"),
        ("node_name_prefix", "bad-prefix_", "node_name_prefix"),
    ],
)
def test_profile_refuses_unsupported_conventions(field: str, value: str, message: str) -> None:
    data = DEFAULT_KEDRO_PROFILE.to_dict()
    data[field] = value
    with pytest.raises(KedroProfileError, match=message):
        KedroArchitectureProfile.from_dict(data)


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        {},
        {"schema_version": "1.0"},
        {**DEFAULT_KEDRO_PROFILE.to_dict(), "templates": "execute.py"},
    ],
)
def test_profile_requires_explicit_identity_and_known_fields(data: object) -> None:
    with pytest.raises(KedroProfileError, match="unknown fields are forbidden"):
        KedroArchitectureProfile.from_dict(data)


@pytest.mark.parametrize("content", [b"{", b"\xff", b"[" * 10000])
def test_profile_reports_unreadable_json(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "profile.json"
    path.write_bytes(content)
    with pytest.raises(KedroProfileError, match="Cannot read Kedro profile"):
        load_kedro_profile(path)


def test_profile_rejects_duplicate_keys_and_oversize_files(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text('{"profile_id":"one","profile_id":"two"}', encoding="utf-8")
    with pytest.raises(KedroProfileError, match="Duplicate Kedro profile field"):
        load_kedro_profile(path)
    path.write_bytes(b" " * (MAX_PROFILE_BYTES + 1))
    with pytest.raises(KedroProfileError, match="size limit"):
        load_kedro_profile(path)
    with pytest.raises(KedroProfileError, match="Cannot read Kedro profile"):
        load_kedro_profile(tmp_path / "missing.json")


@pytest.mark.parametrize("kind", ["duplicate_id", "normalized_name", "invalid_name", "builtin"])
def test_profile_rejects_incompatible_node_names(kind: str) -> None:
    plan = _plan()
    task = plan.task_candidates[0]
    tasks: tuple[TaskCandidate, ...]
    if kind == "duplicate_id":
        tasks = (task, replace(task, name="other"))
    elif kind == "normalized_name":
        tasks = (replace(task, name="K"), replace(task, id="t2", name="\u212a"))
    else:
        tasks = (replace(task, name="bad-name" if kind == "invalid_name" else "print"),)
    with pytest.raises(KedroProfileError, match=r"unique|invalid|shadow"):
        resolve_node_names(replace(plan, task_candidates=tasks), DEFAULT_KEDRO_PROFILE)


@pytest.mark.parametrize(
    ("imports", "message"),
    [
        (("not valid python",), "Cannot check profile"),
        (("value = 1",), "explicit import statements"),
        (("from . import helper",), "relative or wildcard"),
        (("from pkg import *",), "relative or wildcard"),
        (("import pkg as ml_prepare",), "shadow"),
        (("import ml_prepare.submodule",), "shadow"),
    ],
)
def test_profile_explains_import_incompatibility(imports: tuple[str, ...], message: str) -> None:
    with pytest.raises(KedroProfileError, match=message):
        resolve_node_names(replace(_plan(), imports=imports), load_kedro_profile(EXAMPLE))


def test_profile_resolves_explicit_import_aliases_without_importing_packages() -> None:
    plan = replace(
        _plan(), imports=("import missing.module as tool", "from missing import helper as h")
    )
    assert resolve_node_names(plan, DEFAULT_KEDRO_PROFILE) == {"t1": "prepare"}
