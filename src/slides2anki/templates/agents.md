# slides2anki workspace

This folder turns lecture slides into an Anki deck. The `slides2anki` CLI does the deterministic work (PDF text extraction, page images, task files, validation, deck building). You, the AI assistant, write the outline and the cards.

## Start here
- Pending work is listed in `.slides2anki/TODO.md`. Each task file in `.slides2anki/tasks/` is self-contained.
- If `TODO.md` is missing or outdated, run `slides2anki prep` first.

## Files you may write
| Path | Purpose |
|---|---|
| `outline.toml` | topics and the slide files belonging to each; one Anki subdeck per topic |
| `cards/<slug>.json` | the cards for one slide file |
| `checks/*.py` | custom deterministic checks |
| `course.toml` | only when the user asks to change course settings |

Never modify `slides/`, `context/` or `.slides2anki/` by hand.

## Commands
- `slides2anki prep`: extract new or changed slides and write tasks
- `slides2anki validate [cards/x.json ...]`: check cards; run it after every change and fix all issues
- `slides2anki status`: overview of files, topics and cards
- `slides2anki checks`: list available checks
- `slides2anki build`: write the `.apkg` file (the user imports it)

## Card file format
$card_format

## Rules and checks
Users can add rules in two ways:
- Natural-language rules go into `review_rules` in `course.toml`. You check every card against them while writing.
- Rules that can be verified mechanically become a Python check in `checks/`. Every file there not starting with `_` runs on `slides2anki validate`. When the user asks for such a rule, write or extend a check, run it, and fix the cards it flags.

```python
from slides2anki import CheckContext, Issue, check


@check("short-questions", "Questions are at most 200 characters")
def short_questions(ctx: CheckContext):
    for cf, card in ctx.cards():
        if len(card.question) > 200:
            yield Issue("question longer than 200 characters", cf.label, card.id)
```

`ctx.cards(SingleChoice)` filters by card type (`SingleChoice`, `MultipleChoice`, `OpenCard`), `ctx.files` lists the card files and `ctx.course` holds the settings from `course.toml`.
