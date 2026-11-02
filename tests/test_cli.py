import json
import sqlite3
import zipfile
from pathlib import Path

from conftest import SOURCE, single, write_cards
from typer.testing import CliRunner

from slides2anki.cli import app


def test_full_workflow(workspace: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["prep"])
    assert result.exit_code == 0, result.output
    assert "Follow TODO.md" in result.output
    assert "cd slides2anki" in result.output

    (workspace / "outline.toml").write_text(
        f'[[topics]]\ntitle = "Graph Search"\nfiles = ["{SOURCE}"]\n'
    )
    cards = [single(i, "ABCD"[i % 4]) for i in range(4)]
    cards.append(
        {
            "id": "bfs-props",
            "type": "multi",
            "question": "Which hold for **BFS**?",
            "options": ["linear time", "uses a stack", "shortest paths when unweighted"],
            "correct": ["A", "C"],
            "explanation": "See \\( O(V+E) \\).",
            "pages": [2],
            "figure": 2,
        }
    )
    cards.append(
        {
            "id": "dijkstra",
            "type": "open",
            "question": "Precondition of Dijkstra?",
            "answer": "w >= 0",
            "pages": [4],
            "explanation": "x",
        }
    )
    write_cards(workspace, cards)

    assert runner.invoke(app, ["validate"]).exit_code == 0
    assert "Everything is up to date" in runner.invoke(app, ["prep"]).output

    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    apkg = workspace / "decks" / "algorithms.apkg"
    with zipfile.ZipFile(apkg) as z:
        names = z.namelist()
        media = json.loads(z.read("media"))
        z.extract("collection.anki2", workspace)
    assert "s2a_lectures-week-1-01-graphs_p002.jpg" in media.values()
    assert len(names) == 3
    db = sqlite3.connect(workspace / "collection.anki2")
    assert db.execute("select count(*) from notes").fetchone()[0] == 6
    decks = db.execute("select decks from col").fetchone()[0]
    assert "Algorithms::01 Graph Search" in decks
    fields = " ".join(r[0] for r in db.execute("select flds from notes"))
    assert "<strong>BFS</strong>" in fields
    assert "\\( O(V+E) \\)" in fields
    db.close()


def test_build_refuses_invalid(workspace: Path, runner: CliRunner) -> None:
    runner.invoke(app, ["prep"])
    write_cards(workspace, [single(i, "A") for i in range(8)])
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "A is correct in 8/8" in result.output


def test_init_writes_agent_files(workspace: Path) -> None:
    assert (workspace / "AGENTS.md").read_text().startswith("# slides2anki workspace")
    assert (workspace / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    toml = (workspace / "course.toml").read_text()
    assert 'language = "English"' in toml
    assert "answer-position" in toml
