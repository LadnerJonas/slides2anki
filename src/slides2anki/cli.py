import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from slides2anki.build import build as build_deck
from slides2anki.checks import builtin_checks, load_custom_checks
from slides2anki.config import CardType, Checks, Course, Sources
from slides2anki.outline import Outline
from slides2anki.prep import agents_md, scan
from slides2anki.prep import prep as run_prep
from slides2anki.sources import context_candidates, discover, folder_groups, walk
from slides2anki.validate import Report
from slides2anki.validate import validate as run_validate
from slides2anki.workspace import CONFIG_NAME, DEFAULT_DIR, Workspace, WorkspaceError

app = typer.Typer(
    help="Turn lecture slides into Anki decks with the AI coding CLI of your choice.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

PASTE_FIRST = "Follow TODO.md. Show me the outline before writing cards."
PASTE = "Follow TODO.md"
DEFAULT_SLIDES = Sources().slides
MAX_CANDIDATES = 15

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


def _choose_sources(base: Path, skip: Path) -> tuple[list[str], list[str]]:
    files = list(walk(base, skip))
    pdfs = [f for f in files if f.lower().endswith(".pdf")]
    slides, context = list(DEFAULT_SLIDES), []
    if not pdfs:
        console.print(
            "\n[yellow]No PDFs found yet.[/] Add them anywhere in the lecture folder later."
        )
    groups = folder_groups(pdfs)
    if len(groups) > 1:
        console.print(f"\n[bold]Found {len(pdfs)} PDFs[/] in {base}:")
        for i, g in enumerate(groups, 1):
            console.print(f"  {i}  {escape(g.label)}  [dim]{g.count}[/]")
        picked = _pick_numbers(
            "Make cards from which folders? Numbers or 'all'", len(groups), default="all"
        )
        if len(picked) < len(groups):
            slides = [groups[i].pattern for i in picked]
            rest = [g for i, g in enumerate(groups) if i not in picked]
            console.print("\n[bold]Context only[/] (e.g. past exams, module description):")
            for i, g in enumerate(rest, 1):
                console.print(f"  {i}  {escape(g.label)}")
            chosen = _pick_numbers(
                "Use which as context? Numbers or 'none'", len(rest), default="none"
            )
            context = [rest[i].pattern for i in chosen]
    if candidates := context_candidates(files):
        shown = candidates[:MAX_CANDIDATES]
        console.print(
            "\n[bold]Course pages and notes[/] (help to structure topics, e.g. saved Moodle page):"
        )
        for i, c in enumerate(shown, 1):
            console.print(f"  {i}  {escape(c)}")
        if len(candidates) > len(shown):
            console.print(
                f"  [dim]… {len(candidates) - len(shown)} more, add them in course.toml[/]"
            )
        chosen = _pick_numbers(
            "Use which as context? Numbers, 'all' or 'none'", len(shown), default="none"
        )
        context += [shown[i] for i in chosen]
    return slides, context


def _locate(lecture: Path, folder: str) -> tuple[Path, Path]:
    base = lecture.resolve()
    if not base.is_dir():
        console.print(f"[red]{base} is not a folder.[/]")
        raise typer.Exit(2)
    root = (base / folder).resolve()
    if root == base or not root.is_relative_to(base):
        console.print("[red]--dir must name a subfolder of the lecture folder.[/]")
        raise typer.Exit(2)
    if (root / CONFIG_NAME).exists():
        console.print(f"[red]{root / CONFIG_NAME} already exists.[/]")
        raise typer.Exit(1)
    return base, root


def _create(root: Path, course: Course) -> Workspace:
    ws = Workspace(root)
    for directory in (ws.context, ws.cards, ws.checks):
        directory.mkdir(parents=True, exist_ok=True)
    course.save(ws.config_file)
    (root / "AGENTS.md").write_text(agents_md(), "utf-8")
    for alias in ("CLAUDE.md", "GEMINI.md"):
        (root / alias).write_text("@AGENTS.md\n", "utf-8")
    (ws.checks / "_example.py").write_text(EXAMPLE_CHECK, "utf-8")
    return ws


@app.command()
def init(
    lecture: Annotated[
        Path, typer.Argument(help="Lecture folder with your slides (any structure)")
    ] = Path(),
    folder: Annotated[
        str, typer.Option("--dir", help="Name of the slides2anki folder inside it")
    ] = DEFAULT_DIR,
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
    slides: Annotated[
        list[str] | None, typer.Option("--slides", help="Glob for slide PDFs, e.g. 'Lectures/**'")
    ] = None,
    context: Annotated[
        list[str] | None, typer.Option("--context", help="Glob for context files")
    ] = None,
    no_input: Annotated[bool, typer.Option("--no-input", help="Never prompt")] = False,
) -> None:
    """Set up slides2anki in a lecture folder. Only its own subfolder is ever written."""
    base, root = _locate(lecture, folder)

    def missing(flag: str) -> typer.Exit:
        console.print(f"[red]--{flag} is required with --no-input[/]")
        return typer.Exit(2)

    def need(value: str | None, label: str, default: str = "") -> str:
        if value is not None:
            return value
        return default if no_input else _ask(label, default=default)

    console.print(f"Lecture folder: [bold]{base}[/] (read only)")
    console.print(f"slides2anki folder: [bold]{root}[/]\n")
    name = need(name, "Course name", base.name)
    if language is None and no_input:
        raise missing("language")
    language = language or _ask("Card language (e.g. English, German)", required=True)
    if card_type:
        types = list(dict.fromkeys(card_type))
    elif no_input:
        raise missing("type")
    else:
        types = _choose_types()
    if slides is None and context is None and not no_input:
        slide_globs, context_globs = _choose_sources(base, root)
    else:
        slide_globs, context_globs = slides or list(DEFAULT_SLIDES), context or []
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
        sources=Sources(
            root=os.path.relpath(base, root).replace(os.sep, "/"),
            slides=slide_globs,
            context=context_globs,
        ),
    )
    found = discover(_create(root, course))
    console.print(f"\n[green]Created {root}[/] ({len(found.slides)} slide PDFs found)\n")
    console.print("Next: run [bold]slides2anki prep[/] (anywhere in the lecture folder).")
    console.print(
        "[dim]New PDFs anywhere in the lecture folder are picked up on the next prep; "
        "which files count is set under \\[sources] in course.toml.[/]"
    )


@app.command()
def prep() -> None:
    """Extract new or changed slides and write tasks for your AI CLI."""
    ws = _workspace()
    with console.status("Extracting slides…"):
        result = run_prep(ws)
    if result.ignored:
        sample = ", ".join(escape(r) for r in result.ignored[:3]) + (
            ", …" if len(result.ignored) > 3 else ""
        )
        console.print(
            f"[dim]{len(result.ignored)} PDF(s) not matched by \\[sources] in course.toml: "
            f"{sample}[/]"
        )
    if not result.files:
        console.print(f"[yellow]No slide PDFs found in {ws.base}.[/]")
        return
    for info in result.files:
        if info.extracted:
            extra = f", {len(info.doc.sparse)} without text" if info.doc.sparse else ""
            console.print(
                f"  extracted {escape(info.doc.source)} ({len(info.doc.pages)} pages{extra})"
            )
    tasks = int(result.outline_task) + len(result.card_tasks)
    if not tasks:
        console.print("[green]Everything is up to date.[/] Run [bold]slides2anki build[/].")
        return
    first_run = result.outline_task and not ws.outline_file.exists()
    here = Path(os.path.relpath(ws.root))
    where = (
        "this folder" if here == Path() else f"[bold]{here.as_posix()}/[/] (cd {here.as_posix()})"
    )
    console.print(f"\n{tasks} task(s) written to [bold]{ws.rel(ws.todo)}[/].")
    console.print(f"\nStart your AI CLI (claude, codex, gemini, …) in {where} and paste:\n")
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
    infos, ignored = scan(ws)
    for info in infos:
        doc = info.doc
        topic = outline.topic_of(doc.source)
        style = {"done": "green", "stale": "yellow", "new": "red"}[info.status]
        table.add_row(
            escape(doc.source),
            str(len(doc.pages)),
            str(len(doc.sparse) or ""),
            f"{topic[0]:02} {topic[1].title}" if topic else "[red]unassigned[/]",
            str(counts.get(doc.slug, "")),
            f"[{style}]{info.status}[/]",
        )
    console.print(table)
    if missing := outline.missing([i.doc.source for i in infos]):
        console.print(f"[yellow]outline.toml lists missing files: {', '.join(missing)}[/]")
    if ignored:
        console.print(f"[dim]{len(ignored)} PDF(s) not matched by \\[sources] in course.toml.[/]")
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
    console.print("[dim]Enable built-in checks in course.toml under \\[checks].enabled.[/]")
