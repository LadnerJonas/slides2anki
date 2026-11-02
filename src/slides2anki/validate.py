from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from slides2anki.cards import CardFile, CardFileError, load_card_file
from slides2anki.checks import (
    REGISTRY,
    Check,
    CheckContext,
    Issue,
    load_custom_checks,
    run_checks,
)
from slides2anki.extract import load_document
from slides2anki.workspace import Workspace


@dataclass(frozen=True)
class Report:
    files: list[CardFile]
    issues: list[Issue]
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def card_count(self) -> int:
        return sum(len(cf.cards) for cf in self.files)


def integrity(ws: Workspace, cf: CardFile) -> list[Issue]:
    issues: list[Issue] = []
    doc = load_document(ws, cf.slug)
    if doc is None:
        return [Issue(f"no extracted slides for {cf.slug!r}; check slides/ and run prep", cf.label)]
    if doc.source != cf.source:
        issues.append(Issue(f"source {cf.source!r} should be {doc.source!r}", cf.label))
    if cf.source_hash != doc.short_sha:
        issues.append(Issue("stale: slides changed since these cards were written", cf.label))
    allowed = set(ws.course.card_types)
    for card_id, n in Counter(c.id for c in cf.cards).items():
        if n > 1:
            issues.append(Issue(f"id used {n} times", cf.label, card_id))
    for card in cf.cards:
        if card.type not in allowed:
            issues.append(
                Issue(f"card type {card.type!r} not enabled in course.toml", cf.label, card.id)
            )
        refs = [*card.pages, *([card.figure] if card.figure else [])]
        if bad := [p for p in refs if p > len(doc.pages)]:
            issues.append(Issue(f"pages {bad} exceed {len(doc.pages)} slides", cf.label, card.id))
    return issues


def selected_checks(ws: Workspace) -> tuple[list[Check], list[Issue]]:
    custom, issues = load_custom_checks(ws.checks)
    course = ws.course
    chosen: list[Check] = []
    for name in course.checks.enabled:
        if c := REGISTRY.get(name):
            if c.applies_to(course.card_types):
                chosen.append(c)
        else:
            issues.append(Issue(f"unknown check {name!r} in course.toml"))
    return chosen + custom, issues


def validate(ws: Workspace, paths: list[Path] | None = None) -> Report:
    targets = paths or sorted(ws.cards.glob("*.json"))
    files: list[CardFile] = []
    issues: list[Issue] = []
    for path in targets:
        try:
            files.append(load_card_file(path))
        except CardFileError as e:
            issues += [Issue(p, f"{path.parent.name}/{path.name}") for p in e.problems]
        except OSError as e:
            issues.append(Issue(f"cannot read: {e.strerror}", str(path)))
    for cf in files:
        issues += integrity(ws, cf)
    checks, check_issues = selected_checks(ws)
    issues += check_issues
    issues += run_checks(CheckContext(files, ws.course), checks)
    return Report(files, issues, checks)
