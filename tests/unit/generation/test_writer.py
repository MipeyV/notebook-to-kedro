"""Publication failures must not expose partial projects or overwrite destinations."""

from pathlib import Path

import pytest

from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.generation import writer


def test_writer_publishes_complete_files_and_returns_final_paths(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_bytes(b"value\n1\n")
    root = tmp_path / "nested" / "project"
    paths = writer.write_project(
        root,
        {Path("src/package.py"): "value = 1\n"},
        ((source, Path("data/input.csv")),),
    )
    assert paths == (root / "src/package.py", root / "data/input.csv")
    assert paths[0].read_bytes() == b"value = 1\n"
    assert paths[1].read_bytes() == source.read_bytes()
    assert list(root.parent.iterdir()) == [root]


@pytest.mark.parametrize(
    "target",
    [
        ".",
        "../outside",
        "/outside",
        "C:outside",
        "C:/outside",
        "\\\\host\\share\\file",
        "folder\\..\\outside",
        "bad\x00file",
        "bad\nfile",
        "bad\rfile",
        "bad\tfile",
        "data/file:stream",
        "main.py.",
        "main.py ",
        "NUL",
        "data/con.txt",
        "COM1/data.csv",
        "LPT².csv",
    ],
)
def test_writer_refuses_noncontained_paths_before_io(tmp_path: Path, target: str) -> None:
    with pytest.raises(ProjectGenerationError, match="relative contained path"):
        writer.write_project(tmp_path / "project", {Path(target): "content"})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("target", ["data.csv", "DATA.CSV", "data.csv/nested", "src"])
def test_writer_refuses_file_collisions_before_io(tmp_path: Path, target: str) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(b"1\n")
    with pytest.raises(ProjectGenerationError, match="destinations overlap"):
        writer.write_project(
            tmp_path / "project",
            {Path("data.csv"): "original", Path("src/main.py"): "value = 1"},
            ((source, Path(target)),),
        )
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_writer_preflights_copy_sources(tmp_path: Path, kind: str) -> None:
    source = tmp_path / "input.csv"
    if kind == "directory":
        source.mkdir()
    with pytest.raises(ProjectGenerationError, match="not a file"):
        writer.write_project(
            tmp_path / "project", {Path("main.py"): "pass"}, ((source, Path("data.csv")),)
        )
    assert not (tmp_path / "project").exists()
    assert not list(tmp_path.glob(".notebook-to-kedro-*"))


@pytest.mark.parametrize("kind", ["file", "directory", "broken_symlink"])
def test_writer_refuses_existing_destinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    root = tmp_path / "project"
    if kind == "file":
        root.write_bytes(b"keep")
    elif kind == "directory":
        root.mkdir()
        (root / "keep").write_bytes(b"keep")
    else:
        # Windows may not grant symlink creation to the test account.
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == root)
    with pytest.raises(ProjectGenerationError, match="Destination already exists"):
        writer.write_project(root, {Path("new.py"): "pass"})
    if kind == "file":
        assert root.read_bytes() == b"keep"
    elif kind == "directory":
        assert (root / "keep").read_bytes() == b"keep"
        assert not (root / "new.py").exists()


@pytest.mark.parametrize("failure", ["write", "copy", "publish", "parent"])
def test_writer_cleans_preparation_after_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(b"1\n")
    root = tmp_path / "project"

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated disk failure")

    if failure == "write":
        monkeypatch.setattr(Path, "write_text", fail)
    elif failure == "copy":
        monkeypatch.setattr("notebook_to_kedro.generation.writer.shutil.copyfile", fail)
    elif failure == "publish":
        monkeypatch.setattr(Path, "rename", fail)
    else:
        parent = tmp_path / "occupied"
        parent.write_bytes(b"keep")
        root = parent / "project"
    with pytest.raises(ProjectGenerationError, match="Cannot publish project"):
        writer.write_project(root, {Path("main.py"): "pass"}, ((source, Path("data.csv")),))
    assert not root.exists()
    assert not list(tmp_path.glob(".notebook-to-kedro-*"))
    assert source.read_bytes() == b"1\n"


def test_writer_preserves_destination_created_during_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    original_write = Path.write_text

    def concurrent_write(path: Path, content: str, **_kwargs: object) -> int:
        root.mkdir()
        (root / "keep").write_bytes(b"keep")
        return original_write(path, content, encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", concurrent_write)
    with pytest.raises(ProjectGenerationError, match="Destination already exists"):
        writer.write_project(root, {Path("main.py"): "pass"})
    assert (root / "keep").read_bytes() == b"keep"
    assert list(root.iterdir()) == [root / "keep"]
    assert not list(tmp_path.glob(".notebook-to-kedro-*"))
