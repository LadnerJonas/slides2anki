from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from slides2anki.build import build as build_deck
from slides2anki.checks import builtin_checks, load_custom_checks
from slides2anki.config import CardType, Checks, Course
from slides2anki.outline import Outline
from slides2anki.prep import agents_md, scan
from slides2anki.prep import prep as run_prep
from slides2anki.validate import Report
from slides2anki.validate import validate as run_validate
from slides2anki.workspace import CONFIG_NAME, Workspace, WorkspaceError

app = typer.Typer(
    help="Turn lecture slides into Anki decks with the AI coding CLI of your choice.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

PASTE_FIRST = "Follow .slides2anki/TODO.md. Show me the outline before writing cards."
PASTE = "Follow .slides2anki/TODO.md"

EXAMPLE_CHECK = """\
# Files starting with "_" are ignored. Rename to e.g. question_length.py to enable.
from slides2anki import CheckContext, Issue, check


@check("question-length", "Questions are at most 200 characters")
def question_length(ctx: CheckContext):
    for cf, card in ctx.cards():
        if len(card.question) > 200:
            yield Issue("question longer than 200 characters", cf.label, card.id)
"""


def _workspace() -> Workspace:
    try:
        return Workspace.find()
    except WorkspaceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(2) from None


def _ask(label: str, *, required: bool = False, default: str = "") -> str:
    while True:
        value = typer.prompt(label, default=default, show_default=bool(default))
        if value.strip() or not required:
            return value.strip()


def _pick_numbers(prompt: str, count: int, *, default: str | None = None) -> list[int]:
    while True:
        raw = (
            typer.prompt(prompt, default=default or "", show_default=bool(default)).strip().lower()
        )
        if raw == "all":
            return list(range(count))
        if raw == "none":
            return []
        try:
            picked = sorted({int(x) - 1 for x in raw.replace(",", " ").split()})
        except ValueError:
            picked = []
        if picked and all(0 <= i < count for i in picked):
            return picked
        console.print("[yellow]Enter numbers from the list, e.g. 1,3[/]")


def _choose_types() -> list[CardType]:
    console.print("\n[bold]Card types[/] (pick one or more):")
    options = list(CardType)
    for i, t in enumerate(options, 1):
        console.print(f"  {i}  {t.label}")
    return [options[i] for i in _pick_numbers("Your choice, e.g. 1,3", len(options))]


def _choose_checks(types: list[CardType]) -> list[str]:
    available = builtin_checks(types)
    console.print(
        "\n[bold]Deck checks[/] (run by `slides2anki validate`; your AI CLI fixes what they flag):"
    )
    for i, c in enumerate(available, 1):
        console.print(f"  {i}  [cyan]{c.name}[/]: {c.description}")
    picked = _pick_numbers("Enable which? Numbers, 'all' or 'none'", len(available), default="all")
    return [available[i].name for i in picked]


def _ask_rules() -> list[str]:
    console.print(
        "\n[bold]Own rules[/] for the AI to follow and check, one per line, empty line to finish.\n"
        "[dim]e.g. 'Start every explanation with the responsible author' or "
        "'Give the English term in brackets after German terms'[/]"
    )
    rules = []
    while rule := _ask(f"Rule {len(rules) + 1}"):
        rules.append(rule)
    return rules


@app.command()
def init(
    directory: Annotated[Path, typer.Argument(help="Course folder to create or use")] = Path(),
    name: Annotated[str | None, typer.Option(help="Course name, used as the root deck")] = None,
    language: Annotated[str | None, typer.Option(help="Language of the cards")] = None,
    card_type: Annotated[
        list[CardType] | None, typer.Option("--type", help="Allowed card type")
    ] = None,
    style: Annotated[str | None, typer.Option(help="Card mix or focus, in your own words")] = None,
    audience: Annotated[str | None, typer.Option(help="Who studies the cards")] = None,
    exam: Annotated[str | None, typer.Option(help="Exam format notes")] = None,
    check: Annotated[
        list[str] | None, typer.Option("--check", help="Check to enable, or 'all'")
    ] = None,
    rule: Annotated[list[str] | None, typer.Option("--rule", help="Own rule for the AI")] = None,
    no_input: Annotated[bool, typer.Option("--no-input", help="Never prompt")] = False,
) -> None:
    """Create a course workspace (asks a few questions)."""
    root = directory.resolve()
    if (root / CONFIG_NAME).exists():
        console.print(f"[red]{root / CONFIG_NAME} already exists.[/]")
        raise typer.Exit(1)

    def missing(flag: str) -> typer.Exit:
        console.print(f"[red]--{flag} is required with --no-input[/]")
        return typer.Exit(2)

    def need(value: str | None, label: str, default: str = "") -> str:
        if value is not None:
            return value
        return default if no_input else _ask(label, default=default)

    name = need(name, "Course name", root.name)
    if language is None and no_input:
        raise missing("language")
    language = language or _ask("Card language (e.g. English, German)", required=True)
    if card_type:
        types = list(dict.fromkeys(card_type))
    elif no_input:
        raise missing("type")
    else:
        types = _choose_types()
    if style is None and not no_input:
        console.print(
            "\n[dim]Describe the card mix or focus in your own words, e.g. 'mostly single choice, "
            "some free text for proofs; focus on definitions and algorithms'.[/]"
        )
    style = need(style, "Card style (optional)")
    audience = need(audience, "Audience (optional, e.g. 'CS master students')")
    exam = need(exam, "Exam format (optional, e.g. 'closed book, single choice, 90 min')")
    available = [c.name for c in builtin_checks(types)]
    if check is not None:
        checks = available if "all" in check else check
    else:
        checks = available if no_input else _choose_checks(types)
    rules = rule if rule is not None else ([] if no_input else _ask_rules())

    course = Course(
        name=name,
        language=language,
        card_types=types,
        style=style,
        audience=audience,
        exam=exam,
        review_rules=rules,
        checks=Checks(enabled=checks),
    )
    ws = Workspace(root)
    for folder in (ws.slides, ws.context, ws.cards, ws.checks):
        folder.mkdir(parents=True, exist_ok=True)
    course.save(ws.config_file)
    (root / "AGENTS.md").write_text(agents_md(), "utf-8")
    for alias in ("CLAUDE.md", "GEMINI.md"):
        (root / alias).write_text("@AGENTS.md\n", "utf-8")
    (ws.checks / "_example.py").write_text(EXAMPLE_CHECK, "utf-8")

    console.print(f"\n[green]Created course workspace in {root}[/]\n")
    console.print("Next:")
    console.print(
        "  1. Put the lecture PDFs into [bold]slides/[/] (any file names, subfolders are fine)"
    )
    console.print("  2. Optional: save the course page or syllabus into [bold]context/[/]")
    console.print("  3. Run [bold]slides2anki prep[/]")


@app.command()
def prep() -> None:
    """Extract new or changed slides and write tasks for your AI CLI."""
    ws = _workspace()
    with console.status("Extracting slides…"):
        result = run_prep(ws)
    if not result.files:
        console.print("[yellow]No PDFs in slides/ yet.[/]")
        return
    for info in result.files:
        if info.extracted:
            extra = f", {len(info.doc.sparse)} without text" if info.doc.sparse else ""
            console.print(f"  extracted {info.doc.source} ({len(info.doc.pages)} pages{extra})")
    tasks = int(result.outline_task) + len(result.card_tasks)
    if not tasks:
        console.print("[green]Everything is up to date.[/] Run [bold]slides2anki build[/].")
        return
    console.print(f"\n{tasks} task(s) written to [bold]{ws.rel(ws.todo)}[/].")
    first_run = result.outline_task and not ws.outline_file.exists()
    console.print(
        "\nPaste this into your AI CLI (claude, codex, gemini, …) started in this folder:\n"
    )
    console.print(f"  [bold cyan]{PASTE_FIRST if first_run else PASTE}[/]\n")
    console.print("Afterwards run [bold]slides2anki build[/].")


def _print_report(report: Report) -> None:
    for issue in report.issues:
        console.print(f"[red]✗[/] {issue}")
    summary = (
        f"{report.card_count} cards in {len(report.files)} file(s), {len(report.checks)} check(s)"
    )
    if report.ok:
        console.print(f"[green]✓ {summary}: no issues[/]")
    else:
        console.print(f"\n[red]{len(report.issues)} issue(s)[/] ({summary})")


@app.command()
def validate(
    paths: Annotated[list[Path] | None, typer.Argument(help="Card files (default: all)")] = None,
) -> None:
    """Check cards against the schema, the slides and the enabled checks."""
    report = run_validate(_workspace(), [p.resolve() for p in paths] if paths else None)
    _print_report(report)
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def build(
    force: Annotated[bool, typer.Option(help="Build even if validation reports issues")] = False,
) -> None:
    """Write the Anki deck (.apkg) for manual import."""
    ws = _workspace()
    report = run_validate(ws)
    if not report.ok:
        _print_report(report)
        if not force:
            console.print("Fix the issues (ask your AI CLI) or use --force.")
            raise typer.Exit(1)
    if not report.files:
        console.print("[yellow]No cards yet. Run slides2anki prep and follow the tasks.[/]")
        raise typer.Exit(1)
    out, count = build_deck(ws, report.files)
    console.print(f"[green]✓ {count} cards → {ws.rel(out)}[/]")
    console.print("Import it in Anki via File → Import. Re-importing updates existing cards.")


@app.command()
def status() -> None:
    """Show slide files, topics and card status."""
    ws = _workspace()
    outline = Outline.load(ws.outline_file)
    report = run_validate(ws)
    counts = {cf.slug: len(cf.cards) for cf in report.files}
    table = Table("File", "Pages", "No text", "Topic", "Cards", "Status")
    infos = scan(ws)
    for info in infos:
        doc = info.doc
        topic = outline.topic_of(doc.source)
        style = {"done": "green", "stale": "yellow", "new": "red"}[info.status]
        table.add_row(
            doc.source,
            str(len(doc.pages)),
            str(len(doc.sparse) or ""),
            f"{topic[0]:02} {topic[1].title}" if topic else "[red]unassigned[/]",
            str(counts.get(doc.slug, "")),
            f"[{style}]{info.status}[/]",
        )
    console.print(table)
    if missing := outline.missing([i.doc.source for i in infos]):
        console.print(f"[yellow]outline.toml lists missing files: {', '.join(missing)}[/]")
    console.print(
        f"{len(report.issues)} validation issue(s)."
        if report.issues
        else "[green]No validation issues.[/]"
    )


@app.command("checks")
def list_checks() -> None:
    """List built-in and custom checks."""
    ws = _workspace()
    enabled = set(ws.course.checks.enabled)
    table = Table("Check", "Enabled", "Description")
    for c in builtin_checks(list(CardType)):
        table.add_row(c.name, "✓" if c.name in enabled else "", c.description)
    custom, issues = load_custom_checks(ws.checks)
    for c in custom:
        table.add_row(f"{c.name} [dim](custom)[/]", "✓", c.description)
    console.print(table)
    for issue in issues:
        console.print(f"[red]✗[/] {issue}")
    console.print("[dim]Enable built-in checks in course.toml under [checks].enabled.[/]")
