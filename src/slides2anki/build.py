import hashlib
import shutil
import tempfile
from pathlib import Path

import genanki

from slides2anki import render
from slides2anki.cards import Card, CardFile, ChoiceCard, OpenCard
from slides2anki.config import Labels
from slides2anki.extract import page_image, slugify
from slides2anki.outline import Outline
from slides2anki.workspace import Workspace

CSS = """
.card { font-family: system-ui, sans-serif; font-size: 18px; line-height: 1.5; text-align: left;
        max-width: 760px; margin: 0 auto; padding: 12px; color: #1f1f1f; background: #fff; }
.question { font-weight: 600; margin-bottom: 8px; }
.hint { font-size: 14px; color: #777; margin-bottom: 10px; }
.options { list-style: none; padding: 0; margin: 0; }
.options li { border: 1px solid #d0d0d0; border-radius: 8px; padding: 8px 12px; margin: 6px 0; }
.options li.correct { border-color: #2e7d32; background: #e8f5e9; font-weight: 600; }
.letter { display: inline-block; width: 1.6em; font-weight: 700; color: #666; }
.answer { margin-top: 10px; }
.explanation { margin-top: 12px; padding-top: 10px; border-top: 1px solid #eee; }
.figure img { max-width: 100%; margin-top: 12px; border: 1px solid #eee; border-radius: 6px; }
.source { margin-top: 12px; font-size: 13px; color: #888; }
pre, code { font-family: ui-monospace, monospace; font-size: 0.9em; }
pre { background: #f5f5f5; padding: 8px; border-radius: 6px; overflow-x: auto; }
.nightMode .card { color: #ddd; background: #2b2b2b; }
.nightMode .options li { border-color: #555; }
.nightMode .options li.correct { border-color: #66bb6a; background: #1b3a1e; }
.nightMode pre { background: #1e1e1e; }
"""

_BACK_TAIL = """
<div class="explanation">{{Explanation}}</div>
{{#Figure}}<div class="figure">{{Figure}}</div>{{/Figure}}
<div class="source">{{Source}}</div>
"""

_CHOICE_HEAD = '<div class="question">{{Question}}</div><div class="hint">{{Hint}}</div>'

CHOICE_MODEL = genanki.Model(
    1_730_000_001,
    "slides2anki choice",
    fields=[
        {"name": n}
        for n in ("Question", "Hint", "Options", "Solution", "Explanation", "Source", "Figure")
    ],
    templates=[
        {
            "name": "Choice",
            "qfmt": _CHOICE_HEAD + "{{Options}}",
            "afmt": _CHOICE_HEAD + "{{Solution}}" + _BACK_TAIL,
        }
    ],
    css=CSS,
)

OPEN_MODEL = genanki.Model(
    1_730_000_002,
    "slides2anki open",
    fields=[{"name": n} for n in ("Question", "Answer", "Explanation", "Source", "Figure")],
    templates=[
        {
            "name": "Open",
            "qfmt": '<div class="question">{{Question}}</div>',
            "afmt": '<div class="question">{{Question}}</div><hr id="answer">'
            '<div class="answer">{{Answer}}</div>' + _BACK_TAIL,
        }
    ],
    css=CSS,
)


def stable_id(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:4]) >> 1


def _options(card: ChoiceCard, reveal: bool) -> str:
    rows = []
    for i, (letter, option) in enumerate(zip(card.letters, card.options, strict=True)):
        cls = ' class="correct"' if reveal and i in card.correct_indices else ""
        rows.append(f'<li{cls}><span class="letter">{letter}</span>{render.inline(option)}</li>')
    return f'<ul class="options">{"".join(rows)}</ul>'


def _source(cf: CardFile, card: Card) -> str:
    pages = sorted(set(card.pages))
    span = f"p. {pages[0]}" if len(pages) == 1 else f"pp. {', '.join(map(str, pages))}"
    return f"{cf.source}, {span}"


def note_for(cf: CardFile, card: Card, figure: str, labels: Labels) -> genanki.Note:
    common = {
        "guid": genanki.guid_for(cf.slug, card.id),
        "tags": [t.replace(" ", "_") for t in card.tags],
    }
    explanation, source = render.block(card.explanation), _source(cf, card)
    match card:
        case OpenCard():
            fields = [
                render.inline(card.question),
                render.block(card.answer),
                explanation,
                source,
                figure,
            ]
            return genanki.Note(model=OPEN_MODEL, fields=fields, **common)
        case ChoiceCard():
            fields = [
                render.inline(card.question),
                getattr(labels, card.type),
                _options(card, reveal=False),
                _options(card, reveal=True),
                explanation,
                source,
                figure,
            ]
            return genanki.Note(model=CHOICE_MODEL, fields=fields, **common)


def build(ws: Workspace, files: list[CardFile]) -> tuple[Path, int]:
    course = ws.course
    outline = Outline.load(ws.outline_file)
    decks: dict[str, genanki.Deck] = {}
    media: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for cf in files:
            name = outline.deck_name(course.name, cf.source)
            deck = decks.get(name) or decks.setdefault(name, genanki.Deck(stable_id(name), name))
            for card in cf.cards:
                figure = ""
                if card.figure and (image := page_image(ws, cf.slug, card.figure)).is_file():
                    target = Path(tmp) / f"s2a_{cf.slug}_p{card.figure:03}.jpg"
                    if not target.exists():
                        shutil.copyfile(image, target)
                        media.append(str(target))
                    figure = f'<img src="{target.name}">'
                deck.add_note(note_for(cf, card, figure, course.labels))
        ws.decks.mkdir(exist_ok=True)
        out = ws.decks / f"{slugify(course.name)}.apkg"
        package = genanki.Package([decks[n] for n in sorted(decks)], media_files=media)
        package.write_to_file(out)
    return out, sum(len(cf.cards) for cf in files)
