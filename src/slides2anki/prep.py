import json
import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from string import Template

from slides2anki.cards import peek_source_hash
from slides2anki.config import CardType, Course, Labels
from slides2anki.extract import Document, context_texts, extract_slides, page_image, slide_files
from slides2anki.outline import Outline
from slides2anki.workspace import Workspace

PREVIEW_CHARS = 1500
CONTEXT_CHARS = 40_000

EXAMPLES: dict[CardType, dict] = {
    CardType.SINGLE: {
        "id": "dijkstra-negative-weights",
        "type": "single",
        "question": "Why can Dijkstra's algorithm fail on graphs with negative edge weights?",
        "options": [
            "A settled vertex can later be reached by a cheaper path",
            "The priority queue cannot store negative keys efficiently",
            "Negative weights always create cycles in directed graphs",
            "Relaxation is undefined when an edge weight is negative",
        ],
        "correct": "A",
        "explanation": "Dijkstra finalizes ...",
        "pages": [12],
    },
    CardType.MULTI: {
        "id": "bfs-properties",
        "type": "multi",
        "question": "Which statements about breadth-first search hold?",
        "options": [
            "It finds shortest paths in unweighted graphs",
            "It runs in O(V + E) with adjacency lists",
            "It needs a priority queue",
            "It can detect whether a graph is bipartite",
        ],
        "correct": ["A", "B", "D"],
        "explanation": "...",
        "pages": [3, 4],
        "figure": 4,
    },
    CardType.OPEN: {
        "id": "master-theorem-case-2",
        "type": "open",
        "question": "State case 2 of the master theorem.",
        "answer": "If \\( f(n) = \\Theta(n^{\\log_b a}) \\), then ...",
        "explanation": "...",
        "pages": [21],
    },
}


class FileStatus(StrEnum):
    NEW = "new"
    STALE = "stale"
    DONE = "done"


@dataclass(frozen=True)
class FileInfo:
    doc: Document
    status: FileStatus
    extracted: bool


@dataclass(frozen=True)
class PrepResult:
    files: list[FileInfo]
    outline_task: bool
    card_tasks: list[Document]


def _template(name: str) -> Template:
    return Template(files("slides2anki.templates").joinpath(name).read_text("utf-8"))


TYPE_RULES = {
    CardType.SINGLE: (
        "- Single choice: distractors are plausible misconceptions with the same level of detail "
        "and a similar length as the correct option. Vary which letter is correct."
    ),
    CardType.MULTI: (
        "- Multiple choice: every option is a statement that is clearly true or false. Vary how "
        "many are correct (sometimes one, sometimes all) and where they are."
    ),
    CardType.OPEN: (
        "- Free text: the answer is short enough to recall in under a minute; split larger "
        "topics into several cards."
    ),
}


def _example(card_type: CardType) -> str:
    text = json.dumps(EXAMPLES[card_type], indent=2, ensure_ascii=False)
    text = re.sub(
        r"\[\s*(\d+(?:,\s*\d+)*)\s*\]", lambda m: f"[{', '.join(re.findall(r'\d+', m[1]))}]", text
    )
    return "\n".join("    " + line for line in text.splitlines())


def card_format(types: list[CardType]) -> str:
    examples = ",\n".join(_example(t) for t in types)
    return _template("card_format.md").substitute(
        examples=examples, types=", ".join(f"`{t}`" for t in types)
    )


def agents_md() -> str:
    return _template("agents.md").substitute(card_format=card_format(list(CardType)))


def _course_block(course: Course) -> str:
    rows = [
        ("Course", course.name),
        (
            "Card language",
            f"{course.language} (write all card text in it, whatever the slides use)",
        ),
        ("Card types", "; ".join(t.label for t in course.card_types)),
        ("Card style", course.style),
        ("Audience", course.audience),
        ("Exam", course.exam),
    ]
    return "\n".join(f"- {k}: {v}" for k, v in rows if v)


def _material(doc: Document) -> str:
    return "\n".join(
        f"[p{i}] {text}" if text else f"[p{i}] (no text)" for i, text in enumerate(doc.pages, 1)
    )


def card_task(ws: Workspace, info: FileInfo) -> str:
    doc, course = info.doc, ws.course
    card_path = ws.rel(ws.card_file(doc.slug))
    previous = (
        f"\nThe slides changed since `{card_path}` was written. Read it first, keep cards "
        "(and their ids) that still match the slides, fix or drop outdated ones, add cards for "
        "new content, then overwrite the file.\n"
        if info.status is FileStatus.STALE
        else ""
    )
    extra = ""
    if course.review_rules:
        rules = "\n".join(f"- {r}" for r in course.review_rules)
        extra += f"\n## Course rules (check every card against them)\n{rules}\n"
    if doc.sparse:
        images = "\n".join(f"- p{p}: `{ws.rel(page_image(ws, doc.slug, p))}`" for p in doc.sparse)
        extra += (
            "\n## Pages without extractable text\nThese pages are images or scans. Open each "
            f"image and treat what you read as part of the slides:\n{images}\n"
        )
    return _template("card_task.md").substitute(
        source=doc.source,
        card_path=card_path,
        page_count=len(doc.pages),
        previous=previous,
        course=_course_block(course),
        card_format=card_format(course.card_types),
        source_hash=doc.short_sha,
        type_rules="\n".join(TYPE_RULES[t] for t in course.card_types),
        extra=extra,
        material=_material(doc),
    )


def outline_task(ws: Workspace, docs: list[Document], outline: Outline) -> str:
    current = ws.outline_file.read_text("utf-8").strip() if ws.outline_file.is_file() else ""
    context = "\n\n".join(
        f"### {name}\n{text[:CONTEXT_CHARS]}" for name, text in context_texts(ws).items()
    )
    unassigned = set(outline.unassigned([d.source for d in docs]))
    previews = []
    for doc in docs:
        mark = " (new, not yet assigned)" if doc.source in unassigned and current else ""
        text = "\n".join(doc.pages)[:PREVIEW_CHARS]
        previews.append(f"### {doc.source}{mark}\n{len(doc.pages)} pages. Beginning:\n{text}")
    keep = (
        "- Keep existing topics, titles and order; add new files to fitting topics or append new "
        "topics.\n"
        if current
        else ""
    )
    course = ws.course
    labels = (
        f"- Also translate the `[labels]` values in `course.toml` into {course.language}.\n"
        if course.labels == Labels() and not course.language.casefold().startswith("en")
        else ""
    )
    return _template("outline_task.md").substitute(
        labels=labels,
        action="Update" if current else "Create",
        course=ws.course.name,
        keep=keep,
        language=ws.course.language,
        current=f"```toml\n{current}\n```" if current else "(none yet)",
        context=context or "(none: no files in context/)",
        files="\n\n".join(previews),
    )


def scan(ws: Workspace) -> list[FileInfo]:
    out = []
    for path in slide_files(ws):
        doc, extracted = extract_slides(ws, path)
        card_hash = peek_source_hash(ws.card_file(doc.slug))
        if card_hash is None:
            status = FileStatus.NEW
        elif card_hash != doc.short_sha:
            status = FileStatus.STALE
        else:
            status = FileStatus.DONE
        out.append(FileInfo(doc, status, extracted))
    return out


def prep(ws: Workspace) -> PrepResult:
    infos = scan(ws)
    docs = [i.doc for i in infos]
    outline = Outline.load(ws.outline_file)
    needs_outline = bool(outline.unassigned([d.source for d in docs]))
    pending = [i for i in infos if i.status is not FileStatus.DONE]

    ws.tasks.mkdir(parents=True, exist_ok=True)
    for old in ws.tasks.glob("*.md"):
        old.unlink()
    items: list[str] = []
    if needs_outline:
        path = ws.tasks / "outline.md"
        path.write_text(outline_task(ws, docs, outline), "utf-8")
        items.append(f"- [ ] Outline: `{ws.rel(path)}`")
    for info in pending:
        path = ws.tasks / f"cards-{info.doc.slug}.md"
        path.write_text(card_task(ws, info), "utf-8")
        items.append(f"- [ ] Cards for `{info.doc.source}` ({info.status}): `{ws.rel(path)}`")

    if items:
        ws.todo.write_text(
            _template("todo.md").substitute(course=ws.course.name, items="\n".join(items)), "utf-8"
        )
    else:
        ws.todo.unlink(missing_ok=True)
    return PrepResult(infos, needs_outline, [i.doc for i in pending])
