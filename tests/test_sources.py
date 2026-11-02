import hashlib
from pathlib import Path

import pytest
from conftest import LECTURE, SOURCE, make_pdf, single, write_cards
from typer.testing import CliRunner

from slides2anki.cli import app
from slides2anki.sources import _slugs, discover, folder_groups, matches
from slides2anki.workspace import Workspace


@pytest.mark.parametrize(
    ("rel", "pattern", "hit"),
    [
        ("a.pdf", "**/*.pdf", True),
        ("x/y/a.PDF", "**/*.pdf", True),
        ("Lectures/Week 1/a.pdf", "Lectures/**/*.pdf", True),
        ("Lectures/a.pdf", "Lectures/**/*.pdf", True),
        ("Exercises/a.pdf", "Lectures/**/*.pdf", False),
        ("x/a.pdf", "*.pdf", False),
        ("lec_01.pdf", "lec_0?.pdf", True),
    ],
)
def test_glob(rel: str, pattern: str, hit: bool) -> None:
    assert matches(rel, [pattern]) is hit


def test_folder_groups_skip_shared_prefix() -> None:
    rels = ["WS25/Lectures/01.pdf", "WS25/Lectures/w2/02.pdf", "WS25/Exams/2024.pdf", "WS25/x.pdf"]
    groups = [(g.label, g.pattern, g.count) for g in folder_groups(rels)]
    assert groups == [
        ("WS25/Exams/", "WS25/Exams/**/*.pdf", 1),
        ("WS25/Lectures/", "WS25/Lectures/**/*.pdf", 2),
        ("WS25/ (loose files)", "WS25/*.pdf", 1),
    ]


def test_slugs_are_unique() -> None:
    slugs = _slugs(["Week 1/intro.pdf", "week-1/intro.pdf", "a.pdf"])
    assert slugs["a.pdf"] == "a"
    assert len(set(slugs.values())) == 3


def test_discover_skips_workspace_hidden_and_saved_page_folders(workspace: Path) -> None:
    lecture = workspace.parent
    make_pdf(lecture / ".hidden" / "x.pdf", LECTURE)
    make_pdf(workspace / "decks" / "stray.pdf", LECTURE)
    found = discover(Workspace(workspace))
    assert [s.rel for s in found.slides] == [SOURCE]
    assert [p.name for p in found.context] == ["Course Page.html"]
    assert found.ignored == ["Exercises/sheet01.pdf"]


def _snapshot(base: Path, skip: Path) -> dict[str, str]:
    return {
        p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in base.rglob("*")
        if p.is_file() and not p.is_relative_to(skip)
    }


def test_lecture_folder_stays_untouched(workspace: Path, runner: CliRunner) -> None:
    lecture = workspace.parent
    before = _snapshot(lecture, workspace)
    runner.invoke(app, ["prep"])
    write_cards(workspace, [single(i, "ABCD"[i % 4]) for i in range(4)])
    assert runner.invoke(app, ["build"]).exit_code == 0
    assert _snapshot(lecture, workspace) == before
    assert {p.name for p in lecture.iterdir()} == {
        "Lectures",
        "Exercises",
        "Course Page.html",
        "Course Page_files",
        "slides2anki",
    }


@pytest.mark.parametrize("where", ["Lectures/Week 1", "slides2anki/cards"])
def test_find_from_anywhere(workspace: Path, where: str) -> None:
    assert Workspace.find(workspace.parent / where).root == workspace


def test_interactive_init(lecture: Path, runner: CliRunner) -> None:
    answers = [
        "Algo",  # name
        "German",  # language
        "1,3",  # types
        "2",  # slide folders: 1 Exercises/, 2 Lectures/
        "1",  # context: Exercises/
        "all",  # course pages
        "",  # style
        "",  # audience
        "",  # exam
        "all",  # checks
        "",  # rules
    ]
    result = runner.invoke(app, ["init", str(lecture)], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    course = Workspace(lecture / "slides2anki").course
    assert course.card_types == ["single", "open"]
    assert course.sources.slides == ["Lectures/**/*.pdf"]
    assert course.sources.context == ["Exercises/**/*.pdf", "Course Page.html"]
    assert course.sources.root == ".."
    assert "1 slide PDFs found" in result.output


def test_init_rejects_dir_outside(lecture: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["init", str(lecture), "--dir", "..", "--no-input"])
    assert result.exit_code == 2
