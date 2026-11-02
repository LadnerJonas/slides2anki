from pathlib import Path

from conftest import SLUG, SOURCE

from slides2anki.extract import normalize, strip_chrome
from slides2anki.prep import prep
from slides2anki.workspace import Workspace


def test_normalize() -> None:
    assert normalize("a  \t b\n\n\n c\f d") == "a b\nc\nd"


def test_strip_chrome_removes_repeated_lines() -> None:
    pages = [f"Course X\ncontent {i}\nTUM" for i in range(5)]
    assert strip_chrome(pages) == [f"content {i}" for i in range(5)]


def test_prep_extracts_and_writes_tasks(workspace: Path) -> None:
    ws = Workspace(workspace)
    result = prep(ws)
    doc = result.files[0].doc
    assert [i.doc.source for i in result.files] == [SOURCE]
    assert len(doc.pages) == 4
    assert "Breadth-first search" in doc.pages[1]
    assert doc.sparse == [3]
    assert (workspace / f".cache/pages/{SLUG}/p003.jpg").is_file()
    assert result.outline_task
    task = (workspace / f".cache/tasks/cards-{SLUG}.md").read_text()
    assert doc.short_sha in task
    assert "p003.jpg" in task
    assert "[p2] Breadth-first search" in task
    assert "TODO" not in task
    assert result.ignored == ["Exercises/sheet01.pdf"]
    outline = (workspace / ".cache/tasks/outline.md").read_text()
    assert "Week 1: Graph Search" in outline
    assert (workspace / "TODO.md").is_file()


def test_prep_is_incremental(workspace: Path) -> None:
    ws = Workspace(workspace)
    prep(ws)
    assert not any(f.extracted for f in prep(ws).files)
