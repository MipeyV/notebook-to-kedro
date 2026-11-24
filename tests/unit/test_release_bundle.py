"""Release pairing, exact artifact contents and no-publication bundle preparation."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]
COMMIT = "a" * 40


@pytest.fixture
def release_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "prepare_release", ROOT / "tools/prepare_release.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "src/notebook_to_kedro").mkdir(parents=True)
    (root / "extensions/vscode/dist/src").mkdir(parents=True)
    (root / "dist").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname="notebook-to-kedro"\nversion="0.2.0"\nrequires-python=">=3.11,<3.14"\n',
        encoding="utf-8",
        newline="\n",
    )
    (root / "uv.lock").write_text(
        '[[package]]\nname="notebook-to-kedro"\nversion="0.2.0"\n', encoding="utf-8", newline="\n"
    )
    (root / "src/notebook_to_kedro/__init__.py").write_text(
        '__version__ = "0.2.0"\n', encoding="utf-8", newline="\n"
    )
    (root / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [0.2.0] - 2026-11-24\n\n### Release overview\n\n"
        "Engine 0.2.0 / extension 0.4.0.\n\n### Fixed\n\nDetailed changes.\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "extensions/vscode/package.json").write_text(
        json.dumps(
            {
                "name": "notebook-to-kedro",
                "publisher": "mipeyv",
                "version": "0.4.0",
                "engines": {"vscode": "^1.145.0"},
            }
        ),
        encoding="utf-8",
    )
    (root / "extensions/vscode/package-lock.json").write_text(
        json.dumps({"version": "0.4.0", "packages": {"": {"version": "0.4.0"}}}), encoding="utf-8"
    )
    (root / "extensions/vscode/dist/src/extension.js").write_text(
        "module.exports = {};\n", encoding="utf-8", newline="\n"
    )
    return root


def _build(
    root: Path, *, wheel_change: str = "", vsix_change: str = "", sdist_change: str = ""
) -> Path:
    with zipfile.ZipFile(root / "dist/notebook_to_kedro-0.2.0-py3-none-any.whl", "w") as archive:
        content = (root / "src/notebook_to_kedro/__init__.py").read_bytes()
        archive.writestr(
            "notebook_to_kedro/__init__.py", content if wheel_change != "source" else b"changed"
        )
        if wheel_change == "extra":
            archive.writestr("notebook_to_kedro/extra.py", "pass")
        archive.writestr(
            "notebook_to_kedro-0.2.0.dist-info/METADATA",
            "Version: " + ("0.1.0" if wheel_change == "version" else "0.2.0") + "\n",
        )
    with tarfile.open(root / "dist/notebook_to_kedro-0.2.0.tar.gz", "w:gz") as archive:
        for name in (
            "pyproject.toml",
            "uv.lock",
            "CHANGELOG.md",
            "src/notebook_to_kedro/__init__.py",
        ):
            content = b"changed" if name == sdist_change else (root / name).read_bytes()
            info = tarfile.TarInfo("notebook_to_kedro-0.2.0/" + name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    vsix = root / "notebook-to-kedro-0.4.0.vsix"
    with zipfile.ZipFile(vsix, "w") as archive:
        metadata = json.loads((root / "extensions/vscode/package.json").read_text())
        if vsix_change == "metadata":
            metadata["contributes"] = {"unexpected": "command"}
        archive.writestr("extension/package.json", json.dumps(metadata))
        archive.writestr(
            "extension/dist/src/extension.js",
            b"changed"
            if vsix_change == "source"
            else (root / "extensions/vscode/dist/src/extension.js").read_bytes(),
        )
        if vsix_change == "extra":
            archive.writestr("extension/dist/src/extra.js", "unexpected")
    return vsix


def test_bundle_pairs_versions_and_hashes_exact_published_bytes(
    checkout: Path, release_tool: ModuleType
) -> None:
    vsix = _build(checkout)
    output = checkout / "generated/bundle"
    manifest = release_tool.prepare_release(
        checkout, checkout / "dist", vsix, output, commit=COMMIT, tag="v0.2.0"
    )
    assert manifest["engine_version"] == "0.2.0"
    assert manifest["extension_version"] == "0.4.0"
    assert manifest["prerelease"] is True
    assert manifest["source_commit"] == COMMIT
    assert len(list(output.iterdir())) == 6
    assert json.loads((output / "release-manifest.json").read_text()) == manifest
    for line in (output / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected
    notes = (output / "RELEASE_NOTES.md").read_text()
    assert "Engine 0.2.0 / extension 0.4.0" in notes
    assert "Detailed changes" not in notes
    assert "/blob/v0.2.0/CHANGELOG.md" in notes
    with pytest.raises(ProjectGenerationError, match="exists"):
        release_tool.prepare_release(checkout, checkout / "dist", vsix, output, commit=COMMIT)


@pytest.mark.parametrize("change", ["source", "extra", "version"])
def test_wrong_wheel_refuses_bundle(checkout: Path, release_tool: ModuleType, change: str) -> None:
    vsix = _build(checkout, wheel_change=change)
    with pytest.raises(ValueError, match="Wheel"):
        release_tool.prepare_release(
            checkout, checkout / "dist", vsix, checkout / "generated/bundle", commit=COMMIT
        )
    assert not (checkout / "generated").exists()


@pytest.mark.parametrize("change", ["metadata", "source", "extra"])
def test_wrong_vsix_refuses_bundle(checkout: Path, release_tool: ModuleType, change: str) -> None:
    vsix = _build(checkout, vsix_change=change)
    with pytest.raises(ValueError, match="VSIX"):
        release_tool.prepare_release(
            checkout, checkout / "dist", vsix, checkout / "generated/bundle", commit=COMMIT
        )
    assert not (checkout / "generated").exists()


@pytest.mark.parametrize("change", ["pyproject.toml", "src/notebook_to_kedro/__init__.py"])
def test_wrong_sdist_refuses_bundle(checkout: Path, release_tool: ModuleType, change: str) -> None:
    vsix = _build(checkout, sdist_change=change)
    with pytest.raises(ValueError, match="Source distribution"):
        release_tool.prepare_release(
            checkout, checkout / "dist", vsix, checkout / "generated/bundle", commit=COMMIT
        )


@pytest.mark.parametrize(
    "change",
    [
        "export",
        "uv",
        "npm",
        "changelog",
        "overview",
        "tag",
        "commit",
        "artifacts",
        "output",
        "uncompiled",
    ],
)
def test_metadata_and_publication_inputs_fail_before_writes(
    checkout: Path, release_tool: ModuleType, change: str
) -> None:
    vsix = _build(checkout)
    tag, commit = "v0.2.0", COMMIT
    output = checkout / "generated/bundle"
    if change == "export":
        (checkout / "src/notebook_to_kedro/__init__.py").write_text('__version__="0.1.0"\n')
    elif change == "uv":
        (checkout / "uv.lock").write_text(
            '[[package]]\nname="notebook-to-kedro"\nversion="0.1.0"\n'
        )
    elif change == "npm":
        (checkout / "extensions/vscode/package-lock.json").write_text(
            '{"version":"old","packages":{"":{"version":"old"}}}'
        )
    elif change == "changelog":
        (checkout / "CHANGELOG.md").write_text("## [Unreleased]\n")
    elif change == "overview":
        (checkout / "CHANGELOG.md").write_text(
            "## [0.2.0] - 2026-11-24\n\n### Added\nOther notes\n"
        )
    elif change == "tag":
        tag = "v0.1.0"
    elif change == "commit":
        commit = "short"
    elif change == "artifacts":
        (checkout / "dist/old.whl").write_bytes(b"old")
    elif change == "output":
        output = checkout / "src/bundle"
    else:
        (checkout / "extensions/vscode/dist/src/extension.js").unlink()
    with pytest.raises(ValueError, match=r"version|changelog|Tag|SHA|Build|output|Compile"):
        release_tool.prepare_release(
            checkout, checkout / "dist", vsix, output, commit=commit, tag=tag
        )
    assert not output.exists()


def test_cli_only_prepares_local_assets(
    checkout: Path, release_tool: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    vsix = _build(checkout)
    output = checkout / "generated/bundle"
    assert (
        release_tool.main(
            [
                "--root",
                str(checkout),
                "--artifacts",
                str(checkout / "dist"),
                "--vsix",
                str(vsix),
                "--output",
                str(output),
                "--commit",
                COMMIT,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["tag"] == "v0.2.0"


def test_post_copy_change_is_not_accepted(
    checkout: Path, release_tool: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    vsix = _build(checkout)
    original = release_tool.write_project

    def changed(root: Path, *args: Any) -> tuple[Path, ...]:
        result: tuple[Path, ...] = original(root, *args)
        (root / vsix.name).write_bytes(b"changed during publication")
        return result

    monkeypatch.setattr(release_tool, "write_project", changed)
    with pytest.raises(ValueError, match="changed while copying"):
        release_tool.prepare_release(
            checkout, checkout / "dist", vsix, checkout / "generated/bundle", commit=COMMIT
        )
