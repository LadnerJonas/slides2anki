import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slides2anki.cli import app


def make_pdf(path: Path, pages: list[list[str]]) -> Path:
    """Write a minimal PDF with one text line per entry (empty list = blank page)."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    font = 3
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for lines in pages:
        ops = "".join(
            f"BT /F1 14 Tf 40 {760 - 20 * i} Td ({line}) Tj ET\n" for i, line in enumerate(lines)
        )
        objects.append(f"<< /Length {len(ops)} >>\nstream\n{ops}endstream")
        content = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>"
        )
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010} 00000 n \n" for o in offsets).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path


LECTURE = [
    ["Algorithms 101", "Lecture 1: Graph Search"],
    ["Breadth-first search explores vertices in order of their distance", "Runs in O(V + E)"],
    [],
    ["Dijkstra's algorithm needs non-negative edge weights", "It uses a priority queue"],
]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def workspace(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> Path:
    result = runner.invoke(
        app,
        [
            "init",
            str(tmp_path),
            "--no-input",
            "--name",
            "Algorithms",
            "--language",
            "English",
            "--type",
            "single",
            "--type",
            "multi",
            "--type",
            "open",
            "--check",
            "all",
        ],
    )
    assert result.exit_code == 0, result.output
    make_pdf(tmp_path / "slides" / "01_graphs.pdf", LECTURE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


QUESTIONS = [
    "What is the running time of breadth-first search?",
    "Which data structure does Dijkstra rely on?",
    "Why must edge weights be non-negative for Dijkstra?",
    "How is a graph usually stored when it is sparse?",
    "When does depth-first search revisit a vertex?",
    "Which traversal yields a topological order?",
    "What makes a heap different from a sorted array?",
    "Where is the minimum stored in a binary min-heap?",
    "Who proposed the shortest-path algorithm with a queue?",
    "Can BFS detect bipartite graphs?",
    "Is every tree a connected acyclic graph?",
    "Which invariant does relaxation maintain?",
]


def single(i: int, correct: str = "A", **extra) -> dict:
    return {
        "id": f"q{i}",
        "type": "single",
        "question": QUESTIONS[i],
        "options": ["first option", "second option", "third option", "fourth option"],
        "correct": correct,
        "explanation": "Because.",
        "pages": [2],
        **extra,
    }


def write_cards(ws: Path, cards: list[dict], source_hash: str | None = None) -> Path:
    doc = json.loads((ws / ".slides2anki/pages/01-graphs/document.json").read_text())
    path = ws / "cards" / "01-graphs.json"
    payload = {
        "source": "01_graphs.pdf",
        "source_hash": source_hash or doc["sha"][:16],
        "cards": cards,
    }
    path.write_text(json.dumps(payload))
    return path
