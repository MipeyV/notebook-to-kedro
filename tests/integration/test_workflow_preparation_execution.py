"""Trusted synthetic prepared orchestration and subsequent explicit Kedro conversion."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from notebook_to_kedro import (
    KedroArchitectureProfile,
    WorkflowCall,
    WorkflowPreparationDefinition,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_preparation_definition,
    load_workflow_regression_contract,
    prepare_functional_workflow,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_package"

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def clean_modules() -> Iterator[None]:
    names = ("example_ml", "orchestration_ml")
    prior = {name: value for name, value in sys.modules.items() if name.split(".")[0] in names}
    for name in prior:
        del sys.modules[name]
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in names:
            del sys.modules[name]
    sys.modules.update(prior)


_NODES = '''"""Existing node functions without an orchestration entrypoint."""
from orchestration_ml import support

def load_values(raw):
    return support.load_values(raw)

def load_settings(raw):
    return support.load_settings(raw)

def evaluate(values, settings, candidate):
    return support.evaluate(values, settings, candidate)
'''

_SUPPORT = """trace = []
fail_at = None
class Value:
    def __init__(self, value):
        self.value = value
def record(name, values):
    trace.append((name, values))
    if fail_at == name:
        raise RuntimeError(name)
def load_values(raw):
    record("values", raw)
    return raw
def load_settings(raw):
    record("settings", raw)
    return raw
def evaluate(values, settings, candidate):
    record("evaluate", (values, settings, candidate))
    return Value(values.value + settings.value + candidate["offset"])
"""


@pytest.mark.integration
@pytest.mark.parametrize("failure", [None, "values", "settings", "evaluate"])
def test_prepared_join_preserves_original_types_identity_order_and_exception_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    package = tmp_path / "orchestration_ml"
    package.mkdir()
    (package / "__init__.py").write_text('"""Trusted synthetic package."""\n')
    (package / "nodes.py").write_text(_NODES)
    (package / "support.py").write_text(_SUPPORT)
    definition = WorkflowPreparationDefinition(
        "orchestration_ml",
        "workflow",
        ("raw_values", "raw_settings", "candidate"),
        (
            WorkflowCall("load_values", (("raw", "raw_values"),), "values"),
            WorkflowCall("load_settings", (("raw", "raw_settings"),), "settings"),
            WorkflowCall(
                "evaluate",
                (("values", "values"), ("settings", "settings"), ("candidate", "candidate")),
                "result",
            ),
        ),
        "result",
    )
    destination = tmp_path / "prepared"
    prepare_functional_workflow(
        package / "nodes.py", definition, destination, project_root=tmp_path
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    support = importlib.import_module("orchestration_ml.support")
    adapter = importlib.import_module("orchestration_ml.workflow_adapter")
    assert adapter.__file__ is not None
    assert Path(adapter.__file__).is_relative_to(destination)
    values, settings, candidate = support.Value(3), support.Value(2), {"offset": 0.5}
    monkeypatch.setattr(support, "fail_at", failure)
    if failure is None:
        result = adapter.workflow(values, settings, candidate)
        assert type(result) is support.Value
        assert result.value == 5.5
    else:
        with pytest.raises(RuntimeError, match=failure):
            adapter.workflow(values, settings, candidate)
    expected = ["values", "settings", "evaluate"]
    if failure is not None:
        expected = expected[: expected.index(failure) + 1]
    assert [name for name, _ in support.trace] == expected
    assert support.trace[0][1] is values
    if len(expected) >= 2:
        assert support.trace[1][1] is settings
    if len(expected) == 3:
        observed = support.trace[2][1]
        assert observed[0] is values
        assert observed[1] is settings
        assert observed[2] is candidate
    assert (package / "nodes.py").read_text() == _NODES


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
def test_explicit_json_contract_can_convert_the_prepared_copy_and_deliver_active_tests(
    tmp_path: Path,
    *,
    custom_profile: bool,
) -> None:
    prepared = tmp_path / "prepared"
    definition = load_workflow_preparation_definition(EXAMPLE / "preparation.json")
    prepare_functional_workflow(
        EXAMPLE / "src/example_ml/transforms.py", definition, prepared, project_root=ROOT
    )
    (prepared / "input.json").write_bytes((EXAMPLE / "input.json").read_bytes())
    # This fixture explicitly supplies JSON I/O after source preparation; preparation infers none.
    configuration = replace(
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        entrypoint=definition.entrypoint,
        source_package="src/example_ml",
        inputs=(("values", "input.json"),),
    )
    profile = (
        KedroArchitectureProfile("test.prepared", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    project = tmp_path / "kedro"
    generate_functional_kedro_project(
        prepared / "src/example_ml/workflow_adapter.py",
        configuration,
        project,
        project_root=prepared,
        package_name="prepared_case",
        architecture_profile=profile,
        regression_contract=load_workflow_regression_contract(EXAMPLE / "regression.json"),
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)

    def run_tests() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(project / ".pytest-runtime"),
                "-q",
            ],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    passed = run_tests()
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "2 passed" in passed.stdout
    report = json.loads((prepared / "workflow-preparation.json").read_text())
    assert report["status"] == "unreviewed_proposal"
    assert report["execution_status"] == "not_run"
    # A changed declaration is observable: swapping the scale/value binding changes both results.
    adapter = project / "src/example_ml/workflow_adapter.py"
    original = adapter.read_text()
    adapter.write_text(
        original.replace("values=values, scale=scale", "values=values, scale=values")
    )
    failed = run_tests()
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert "2 failed" in failed.stdout
    assert (prepared / "src/example_ml/workflow_adapter.py").read_text() == original
