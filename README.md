# slides2anki

Turn the lecture slides you get every week into an Anki deck, with one subdeck per topic. The CLI does the deterministic work. Your AI coding CLI writes the cards: Claude Code, Codex, Gemini CLI, Cursor, Copilot, or any other agent that can read and write files.

```
your lecture folder ──► slides2anki prep ──► AI CLI ──► slides2anki build ──► deck.apkg ──► Anki
(any structure, read    text per page,       writes      validates,
 only)                  page images,         outline +   renders cards
                        task files           cards       + figures
```

- **Any course, any folder:** run it inside the folder where your slides already are, however deeply nested. It only ever writes into its own `slides2anki/` subfolder.
- **Topics from what you have:** folder and file names, an optional saved course page or syllabus, and the slides themselves.
- **Incremental:** only new or changed PDFs produce tasks, and cards for older lectures stay untouched.
- **Any model:** no API keys. You use the AI CLI and subscription you already have.
- **Your card style:** single choice, multiple choice and free text (question, flip, answer), in any language, mixed the way you describe.
- **Verified decks:** statistical checks catch patterns like "the answer is usually B" or "the longest option is correct", and you can add your own rules.
- **Scanned slides:** pages without a text layer are handed to the AI CLI as images, so nothing needs to be installed for OCR.
- **Figures:** a card can show the relevant slide on the answer side.

## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). It runs on Windows, macOS and Linux and needs no other system packages.

```bash
uv tool install git+https://github.com/LadnerJonas/slides2anki
```

## Quick start

Open a terminal in the folder where you keep the course material, for example:

```
Algorithms WS25/
├── Lectures/
│   ├── 01 Introduction.pdf
│   └── Week 2/02_graphs.pdf
├── Exercises/sheet01.pdf
├── Old exams/2024.pdf
└── Moodle course page.html
```

```bash
cd "Algorithms WS25"
slides2anki init
```

`init` asks for the course name, the card language, the card types, your style in your own words, and which checks to enable. It lists the PDFs it found per folder, so you can pick which folders become cards (e.g. `Lectures/`) and which are context only (e.g. `Old exams/`), and it offers saved course pages (HTML, Markdown, text) as context for the topic structure. Everything ends up in `slides2anki/course.toml`, which you can edit later.

Then:

1. Prepare the tasks (from anywhere inside the lecture folder):

   ```bash
   slides2anki prep
   ```

2. Start your AI CLI in the `slides2anki/` folder and paste the line `prep` prints:

   ```bash
   cd slides2anki
   claude    # or codex, gemini, …
   ```

   ```
   Follow TODO.md. Show me the outline before writing cards.
   ```

3. Build the deck and import `slides2anki/decks/<course>.apkg` in Anki (*File → Import*):

   ```bash
   slides2anki build
   ```

## Every week

Download the new PDF anywhere into the lecture folder and run:

```bash
slides2anki prep
```

Paste `Follow TODO.md` into your AI CLI (started in `slides2anki/`), then:

```bash
slides2anki build
```

Re-importing the deck updates existing cards in place. New lectures are added to a fitting topic or get a new one. `prep` also tells you about PDFs that none of your folder patterns match.

## Layout

Your files are only read. All output lives in one folder, so deleting `slides2anki/` removes every trace.

```
Algorithms WS25/            your lecture folder, any structure, never modified
└── slides2anki/
    ├── course.toml         settings: language, card types, style, checks, rules, sources
    ├── outline.toml        topics → slide files (one subdeck per topic), written by the AI, editable
    ├── TODO.md             pending tasks for the AI CLI (written by prep)
    ├── context/            optional extra context: syllabus, exam info (PDF, HTML, MD, TXT)
    ├── cards/<file>.json   the cards per slide file: the source of truth, editable
    ├── checks/*.py         your own checks
    ├── decks/              the built .apkg
    ├── AGENTS.md           instructions for the AI CLI (CLAUDE.md and GEMINI.md point to it)
    └── .cache/             extracted text, page images, task files
```

Which files count is set in `course.toml`. Paths are relative to the lecture folder; `*` and `?` match within one folder, `**` across any number, case-insensitively:

```toml
[sources]
root = ".."                              # the lecture folder, relative to slides2anki/
slides = ["Lectures/**/*.pdf"]           # default: every PDF ("**/*.pdf")
context = ["Old exams/**/*.pdf", "Moodle course page.html"]
exclude = ["**/*solution*"]
```

Hidden folders, saved-page asset folders (`*_files/`) and `slides2anki/` itself are always skipped.

Deck structure: `Course::01 Topic`, `Course::02 Topic`, …

## Card types

| Type | Front | Back |
|---|---|---|
| `single` | question with 3 to 6 options | correct option highlighted, explanation |
| `multi` | question with 3 to 6 options, "select all that apply" | all correct options highlighted, explanation |
| `open` | question | answer, explanation |

Every card can show a slide image (`figure`) on the back, plus its source pages.

Describe the mix in `style`, for example:

- `mostly single choice like the exam; free text only for definitions`
- `only free text, one card per theorem or algorithm, include complexity`
- `exam-style multiple choice with 4 options, about one third of them with all options correct`

## Checks

`slides2anki validate` runs after every card task (the AI CLI calls it itself) and before every build. Some checks always run:

- schema
- unique ids
- page and figure numbers exist
- cards match the current slide version
- only the enabled card types are used

You choose these in `init` or in `course.toml` under `[checks].enabled`:

| Check | What it catches |
|---|---|
| `answer-position` | one letter is correct significantly more or less often than chance |
| `longest-correct` | the longest option is the correct one significantly more often than chance |
| `shortest-correct` | the same for the shortest option |
| `multi-count` | every multiple-choice card has the same number of correct options |
| `duplicates` | near-identical questions anywhere in the deck (threshold `similarity`) |
| `answer-in-question` | the question already contains the answer |
| `explanation` | cards without an explanation |

The pattern checks use an exact test against chance, a Poisson binomial distribution, so 3 of 5 cards with answer A is not flagged, but 10 of 12 is. They run per file and on the whole deck, at significance level `alpha` (default 0.01).

### Your own rules

- **Natural language:** add them to `review_rules` in `course.toml`. They go into every card task, and the AI checks each card against them.
- **Code:** drop a Python file into `checks/` (see `checks/_example.py`), or ask your AI CLI to write it:

```python
from slides2anki import CheckContext, Issue, SingleChoice, check


@check("four-options", "Single-choice cards have exactly four options")
def four_options(ctx: CheckContext):
    for cf, card in ctx.cards(SingleChoice):
        if len(card.options) != 4:
            yield Issue("needs exactly 4 options", cf.label, card.id)
```

## Example prompts

| Goal | Prompt for your AI CLI |
|---|---|
| First run | `Follow TODO.md. Show me the outline before writing cards.` |
| Weekly update | `Follow TODO.md` |
| More practice | `Add about 8 free-text cards to cards/lectures-05-dynamic-programming.json that ask to trace the recurrence on a small input. Then validate.` |
| Change style | `Rewrite cards/lectures-03-*.json as multiple choice and add figures where a diagram is essential.` |
| Exam alignment | `Old exams/2024.pdf is a past exam. Update style in course.toml to match its question types, then regenerate the cards for topics 1 to 4.` |
| New rule | `Every explanation must name the responsible algorithm. Add this as a check in checks/ and fix all cards it flags.` |
| Review | `Review all cards in topic 2 for factual errors against the slides and fix them.` |
| Restructure | `Split topic 3 in outline.toml into "Hashing" and "Search Trees".` |

## Commands

| Command | Does |
|---|---|
| `slides2anki init [LECTURE_DIR]` | create `slides2anki/` in the lecture folder (interactive; `--no-input` with flags such as `--slides`, `--context` for scripts) |
| `slides2anki prep` | extract new or changed PDFs, write `TODO.md` and task files |
| `slides2anki validate [FILES]` | check cards; exits with 1 on issues |
| `slides2anki build` | write `decks/<course>.apkg` (refuses invalid cards unless `--force`) |
| `slides2anki status` | files, topics, card counts, pending work |
| `slides2anki checks` | list built-in and custom checks |

## Notes

- **Editing:** edit `cards/*.json` directly or ask the AI CLI. Card ids are stable, so re-importing updates the existing notes and keeps your review history.
- **Changed slides:** when a PDF changes, `prep` creates a task that keeps still-valid cards and their ids.
- **Moved or renamed PDFs** get a new card file; `validate` reports the orphaned old one, so the AI CLI can move its cards over or you delete it.
- **Commands** work from anywhere inside the lecture folder; they find `slides2anki/` themselves.
- **Copyright:** lecture material is usually copyrighted. Don't publish `context/`, `.cache/` or the deck if it contains slide images.
- **Token use:** a 40-slide lecture is roughly 10k input tokens. Pages without text cost an image each.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest
```

## License

[GPL-3.0-or-later](LICENSE)
