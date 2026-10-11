"""Offline navigation checks for repository Markdown documentation."""

import re
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
INDEX = DOCS / "README.md"
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "JOURNAL.md",
    *sorted(DOCS.rglob("*.md")),
)


def _markdown_source(document: Path) -> str:
    """Exclude fenced examples from the repository's inline-link checks."""
    source = document.read_text(encoding="utf-8")
    return re.sub(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$", "", source)


def _local_links(document: Path) -> list[tuple[Path, str]]:
    """Resolve the simple inline-link syntax used by these documents."""
    links = []
    for target in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", _markdown_source(document)):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        destination = (
            (document.parent / unquote(parsed.path)).resolve() if parsed.path else document
        )
        links.append((destination, unquote(parsed.fragment)))
    return links


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_local_documentation_links_resolve(document: Path) -> None:
    """Every local inline link names an existing file and, if present, heading."""
    for destination, fragment in _local_links(document):
        assert destination.is_relative_to(ROOT), f"Link escapes repository in {document}"
        assert destination.is_file(), f"Missing target {destination} from {document}"
        if fragment:
            headings = re.findall(r"(?m)^#{1,6} (.+)$", _markdown_source(destination))
            anchors = {
                re.sub(r"[^\w -]", "", heading.strip().lower()).replace(" ", "-")
                for heading in headings
            }
            assert fragment in anchors, (
                f"Missing heading #{fragment} in {destination} from {document}"
            )


def test_documentation_index_lists_every_document() -> None:
    """New documentation cannot disappear from the categorized index."""
    indexed = {destination for destination, _ in _local_links(INDEX)}
    expected = set(DOCS.rglob("*.md")) - {INDEX}
    assert expected <= indexed, f"Unindexed documents: {sorted(expected - indexed)}"


def test_package_readme_remains_at_repository_root() -> None:
    """The root introduction stays the package README and links to the docs index."""
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["readme"] == "README.md"
    assert INDEX in {destination for destination, _ in _local_links(ROOT / "README.md")}
