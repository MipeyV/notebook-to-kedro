"""Static functional inspection boundaries and source-container independence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from notebook_to_kedro import analyze_functional_blocks_path
from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.analysis.functional_sources import MAX_PYTHON_BYTES
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalSourceError, NotebookLoadError
from notebook_to_kedro.ir.functional import SourceUnit

ROOT = Path(__file__).parents[3]
EXAMPLES = ROOT / "examples" / "functional_blocks"


def _unit(source: str, unit_id: str = "module") -> SourceUnit:
    return SourceUnit(unit_id, "workflow.py", "python", "a" * 64, source)


def test_container_independent_structure_preserves_distinct_provenance() -> None:
    script = analyze_functional_blocks_path(EXAMPLES / "workflow.py", project_root=ROOT)
    notebook = analyze_functional_blocks_path(EXAMPLES / "workflow.ipynb", project_root=ROOT)
    assert script.complete
    assert notebook.complete
    assert script.structure_sha256 == notebook.structure_sha256
    assert len(script.structure_sha256 or "") == 64
    assert [block.name for block in script.blocks] == ["prepare_values", "summarize"]
    assert script.blocks[0].parameters == ("values", "scale")
    assert script.blocks[0].outputs == ("prepared",)
    assert script.blocks[0].span.start_line == 6
    assert notebook.blocks[0].span.start_line == 1
    assert notebook.blocks[0].span.unit_id == "cell-0002"
    assert notebook.sources[0].cell_id == "cell-0001"
    assert script.sources[0].cell_id is None
    assert script.sources[0].path == "examples/functional_blocks/workflow.py"
    assert script.sources[0].document_sha256 != notebook.sources[0].document_sha256
    assert [(edge.caller_id, edge.callee_id, edge.kind) for edge in script.dependencies] == [
        ("block-0001", "block-0000", "call")
    ]
    payload = json.loads(script.to_json())
    assert payload["complete"]
    assert payload["sources"][0]["source_sha256"] == script.sources[0].source_sha256
    assert payload["sources"][0]["source"] == (EXAMPLES / "workflow.py").read_text()
    assert (
        script.to_json()
        == analyze_functional_blocks_path(EXAMPLES / "workflow.py", project_root=ROOT).to_json()
    )


def test_changed_logic_changes_fingerprint_but_whitespace_does_not() -> None:
    source = "def f(x):\n    y = x * 2\n    return y\n"
    original = analyze_functional_blocks((_unit(source),))
    spaced = analyze_functional_blocks((_unit("\n" + source.replace(" * ", "*")),))
    changed = analyze_functional_blocks((_unit(source.replace("* 2", "* 3")),))
    assert original.structure_sha256 == spaced.structure_sha256
    assert original.structure_sha256 != changed.structure_sha256


def test_named_tuple_returns_annotations_and_reference_edges() -> None:
    source = (
        "def f(x: int) -> tuple:\n    y: int = x\n    y += 1\n    assert y\n    return x, y\n"
        "\ndef g():\n    callback = f\n    return callback"
    )
    result = analyze_functional_blocks((_unit(source),))
    assert result.complete
    assert result.blocks[0].outputs == ("x", "y")
    assert result.dependencies[0].kind == "reference"
    assert "BL103" in {item.code for item in result.diagnostics}


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("def broken(:", "BL001"),
        ("return 1", "BL001"),
        ("print('side effect')", "BL002"),
        ("async def f(x):\n    return x", "BL002"),
        ("class Model:\n    pass", "BL002"),
        ("from .data import x", "BL002"),
        ("from package import *", "BL002"),
        ("import math\nimport math", "BL002"),
        ("import math, math", "BL002"),
        ("def f(x):\n    return x\ndef f(y):\n    return y", "BL002"),
        ("import math as f\ndef f(x):\n    return x", "BL002"),
        ("def f(x=1):\n    return x", "BL003"),
        ("@decorate\ndef f(x):\n    return x", "BL003"),
        ("def f(x, /):\n    return x", "BL003"),
        ("def f(*, x):\n    return x", "BL003"),
        ("def f(*x):\n    return x", "BL003"),
        ("def f(**x):\n    return x", "BL003"),
        ("def f(x: annotate()):\n    return x", "BL003"),
        ("def f(x) -> annotate():\n    return x", "BL003"),
        ("def f(x):\n    pass", "BL003"),
        ("def f(x):\n    return x + 1", "BL003"),
        ("def f(x):\n    return ()", "BL003"),
        ("def f(x):\n    return x, 1", "BL003"),
        ("def f(x):\n    if x:\n        return x\n    return x", "BL003"),
        ("def f(x):\n    for y in x:\n        print(y)\n    return x", "BL004"),
        ("def f(x):\n    y = [v for v in x]\n    return y", "BL004"),
        ("def f(x):\n    x.value = 2\n    return x", "BL004"),
        ("def f(x):\n    x[0] = 2\n    return x", "BL004"),
        ("def f(x):\n    eval(x)\n    return x", "BL004"),
        ("def f(x):\n    y = unknown + x\n    return y", "BL005"),
        ("def f(x):\n    y = z\n    z = x\n    return y", "BL006"),
        ("def f(x):\n    y += x\n    return y", "BL006"),
        ("def f(x):\n    y: int\n    return y", "BL006"),
        ("def f(x):\n    y = f(x)\n    return y", "BL007"),
        ("def f(x):\n    y = g(x)\n    return y\ndef g(x):\n    y = f(x)\n    return y", "BL007"),
        ("def f(callback, x):\n    y = callback(x)\n    return y", "BL008"),
        ("def f(x):\n    y = x[0]()\n    return y", "BL008"),
        ("", "BL009"),
    ],
)
def test_unsupported_source_is_retained_and_never_marked_complete(source: str, code: str) -> None:
    result = analyze_functional_blocks((_unit(source),))
    assert not result.complete
    assert result.structure_sha256 is None
    assert code in {issue.code for issue in result.diagnostics if issue.severity == "error"}
    assert result.sources[0].source == source
    assert json.loads(result.to_json())["structure_sha256"] is None


def test_decoration_and_unicode_spans_keep_original_text() -> None:
    source = "@décorer\r\ndef f(été):\r\n    return été\r\n"
    result = analyze_functional_blocks((_unit(source),))
    block = result.blocks[0]
    assert block.source == source.rstrip("\r\n")
    assert block.span.start_line == 1
    assert block.span.end_line == 3
    assert block.span.end_column == len("    return été".encode())
    assert result.statements[0].source == block.source


def test_imports_are_facts_without_importing_or_executing_sources(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source = (
        "import absent_inspection_dependency.submodule as dependency\n"
        "from missing_package import thing as other\n"
        "def f(x):\n    dependency.fit(x)\n    other(x)\n    return x\n"
        f"open({str(marker)!r}, 'w').close()"
    )
    result = analyze_functional_blocks((_unit(source),))
    assert not marker.exists()
    assert "absent_inspection_dependency" not in sys.modules
    assert result.blocks[0].possible_mutation_targets == ("dependency",)
    assert {"BL101", "BL102", "BL002"} <= {issue.code for issue in result.diagnostics}
    assert result.statements[-1].kind == "unsupported"
    assert result.statements[-1].source.startswith("open(")


def test_duplicate_unit_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        analyze_functional_blocks((_unit(""), _unit("")))


def test_parenthesized_multiline_decorator_span_includes_at_token() -> None:
    source = "@(\n    decorate\n)\n@other\ndef f(x):\n    return x"
    result = analyze_functional_blocks((_unit(source),))
    assert not result.complete
    assert result.blocks[0].span.start_line == 1
    assert result.blocks[0].source == source


def test_python_encoding_raw_hash_and_external_path(tmp_path: Path) -> None:
    path = tmp_path / "encoded.py"
    content = "# coding: latin-1\r\ndef été(x):\r\n    return x\r\n".encode("latin-1")
    path.write_bytes(content)
    result = analyze_functional_blocks_path(path, project_root=tmp_path / "another-root")
    assert result.complete
    assert result.sources[0].path == path.resolve().as_posix()
    assert result.sources[0].document_sha256 == hashlib.sha256(content).hexdigest()
    assert result.sources[0].source_sha256 != result.sources[0].document_sha256
    assert "\r\n" in result.sources[0].source


def test_generic_function_is_reported_without_crashing_on_supported_runtimes() -> None:
    result = analyze_functional_blocks((_unit("def f[T](x: T):\n    return x"),))
    assert not result.complete
    assert {issue.code for issue in result.diagnostics} & {"BL001", "BL003"}


@pytest.mark.parametrize(
    "content",
    [b"\xff", b"# coding: missing_encoding\nx=1", b"x" * (MAX_PYTHON_BYTES + 1)],
    ids=["invalid-utf8", "unknown-encoding", "oversized"],
)
def test_invalid_python_documents_fail_loading(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.py"
    path.write_bytes(content)
    with pytest.raises(FunctionalSourceError):
        analyze_functional_blocks_path(path)


def test_missing_source_and_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(FunctionalSourceError, match="Cannot read"):
        analyze_functional_blocks_path(tmp_path / "missing.py")
    with pytest.raises(FunctionalSourceError, match=r"\.py or \.ipynb"):
        analyze_functional_blocks_path(tmp_path / "workflow.txt")
    with pytest.raises(NotebookLoadError):
        analyze_functional_blocks_path(tmp_path / "missing.ipynb")


def test_cli_inspection_success_blockers_and_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["inspect-blocks", str(EXAMPLES / "workflow.py"), "--project-root", str(ROOT)]) == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    blocked = tmp_path / "blocked.py"
    blocked.write_text("print('do not execute')", encoding="utf-8")
    assert main(["inspect-blocks", str(blocked)]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert not json.loads(captured.out)["complete"]
    assert main(["inspect-blocks", str(tmp_path / "missing.py")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Cannot read Python source" in captured.err
