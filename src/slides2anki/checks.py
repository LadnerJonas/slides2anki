import importlib.util
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from math import fsum
from pathlib import Path
from typing import overload

from slides2anki.cards import Card, CardFile, ChoiceCard, MultipleChoice, OpenCard, SingleChoice
from slides2anki.config import CardType, Course

MIN_SAMPLE = 5


@dataclass(frozen=True)
class Issue:
    message: str
    file: str | None = None
    card: str | None = None

    def __str__(self) -> str:
        where = ":".join(filter(None, (self.file, self.card)))
        return f"{where}: {self.message}" if where else self.message


@dataclass(frozen=True)
class CheckContext:
    files: list[CardFile]
    course: Course

    @overload
    def cards(self) -> Iterator[tuple[CardFile, Card]]: ...
    @overload
    def cards[T](self, kind: type[T]) -> Iterator[tuple[CardFile, T]]: ...
    def cards(self, kind: type = object) -> Iterator[tuple[CardFile, object]]:
        for cf in self.files:
            for card in cf.cards:
                if isinstance(card, kind):
                    yield cf, card

    @property
    def alpha(self) -> float:
        return self.course.checks.alpha


type CheckFn = Callable[[CheckContext], Iterable[Issue]]


@dataclass(frozen=True)
class Check:
    name: str
    description: str
    fn: CheckFn
    types: frozenset[CardType] = field(default_factory=frozenset)
    builtin: bool = True

    def applies_to(self, types: Iterable[CardType]) -> bool:
        return not self.types or bool(self.types & set(types))


REGISTRY: dict[str, Check] = {}
_loading: list[Check] = []


def check(
    name: str, description: str = "", *, types: Iterable[CardType] = ()
) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        builtin = fn.__module__ == __name__
        entry = Check(name, description or name, fn, frozenset(types), builtin)
        if builtin:
            REGISTRY[name] = entry
        else:
            _loading.append(entry)
        return fn

    return register


def builtin_checks(types: Iterable[CardType]) -> list[Check]:
    types = list(types)
    return [c for c in REGISTRY.values() if c.applies_to(types)]


def load_custom_checks(directory: Path) -> tuple[list[Check], list[Issue]]:
    _loading.clear()
    issues: list[Issue] = []
    for path in sorted(directory.glob("*.py")) if directory.is_dir() else []:
        if path.name.startswith("_"):
            continue
        name = f"slides2anki_custom_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            issues.append(Issue(f"failed to load custom check: {e!r}", file=f"checks/{path.name}"))
    custom = list(_loading)
    _loading.clear()
    return custom, issues


def run_checks(ctx: CheckContext, checks: Iterable[Check]) -> list[Issue]:
    issues: list[Issue] = []
    for c in checks:
        try:
            issues.extend(c.fn(ctx))
        except Exception as e:
            issues.append(Issue(f"check {c.name!r} crashed: {e!r}"))
    return issues


def _pmf(ps: list[float]) -> list[float]:
    """Poisson-binomial distribution of the number of successes."""
    dist = [1.0]
    for p in ps:
        nxt = [0.0] * (len(dist) + 1)
        for k, v in enumerate(dist):
            nxt[k] += v * (1 - p)
            nxt[k + 1] += v * p
        dist = nxt
    return dist


def p_upper(ps: list[float], hits: int) -> float:
    return min(1.0, fsum(_pmf(ps)[hits:]))


def p_two_sided(ps: list[float], hits: int) -> float:
    dist = _pmf(ps)
    return min(1.0, 2 * min(fsum(dist[hits:]), fsum(dist[: hits + 1])))


def _scopes[T](ctx: CheckContext, kind: type[T]) -> Iterator[tuple[str, list[T]]]:
    per_file: list[tuple[str, list[T]]] = [
        (cf.label, [c for c in cf.cards if isinstance(c, kind)]) for cf in ctx.files
    ]
    yield from per_file
    if len(per_file) > 1:
        yield "whole deck", [card for _, cards in per_file for card in cards]


def _chance(card: ChoiceCard) -> float:
    return len(card.correct_indices) / len(card.options)


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


KIND_LABEL = {SingleChoice: "single choice", MultipleChoice: "multiple choice"}


@check(
    "answer-position",
    "Correct answers are spread evenly across option letters (no favourite letter)",
    types={CardType.SINGLE, CardType.MULTI},
)
def answer_position(ctx: CheckContext) -> Iterator[Issue]:
    for kind in (SingleChoice, MultipleChoice):
        for scope, cards in _scopes(ctx, kind):
            for pos, letter in enumerate("ABCDEF"):
                rows = [c for c in cards if len(c.options) > pos]
                if len(rows) < MIN_SAMPLE:
                    continue
                ps = [_chance(c) for c in rows]
                hits = sum(pos in c.correct_indices for c in rows)
                if (p := p_two_sided(ps, hits)) < ctx.alpha:
                    yield Issue(
                        f"{KIND_LABEL[kind]}: {letter} is correct in {hits}/{len(rows)} cards, "
                        f"expected about {fsum(ps):.1f} (p={p:.4f}); reorder options",
                        file=scope,
                    )


def _extreme_correct(ctx: CheckContext, pick: Callable[[list[int]], int], word: str):
    for scope, cards in _scopes(ctx, ChoiceCard):
        ps: list[float] = []
        hits = 0
        for c in cards:
            lengths = [len(o) for o in c.options]
            target = pick(lengths)
            if lengths.count(target) != 1:
                continue
            ps.append(_chance(c))
            hits += lengths.index(target) in c.correct_indices
        if len(ps) >= MIN_SAMPLE and (p := p_upper(ps, hits)) < ctx.alpha:
            yield Issue(
                f"the {word} option is correct in {hits}/{len(ps)} choice cards, "
                f"expected about {fsum(ps):.1f} (p={p:.4f}); balance option lengths",
                file=scope,
            )


@check(
    "longest-correct",
    "The correct option is not systematically the longest one",
    types={CardType.SINGLE, CardType.MULTI},
)
def longest_correct(ctx: CheckContext) -> Iterator[Issue]:
    yield from _extreme_correct(ctx, max, "longest")


@check(
    "shortest-correct",
    "The correct option is not systematically the shortest one",
    types={CardType.SINGLE, CardType.MULTI},
)
def shortest_correct(ctx: CheckContext) -> Iterator[Issue]:
    yield from _extreme_correct(ctx, min, "shortest")


@check(
    "multi-count",
    "Multiple-choice cards vary in how many options are correct",
    types={CardType.MULTI},
)
def multi_count(ctx: CheckContext) -> Iterator[Issue]:
    for scope, cards in _scopes(ctx, MultipleChoice):
        counts = {len(c.correct) for c in cards}
        if len(cards) >= MIN_SAMPLE and len(counts) == 1:
            yield Issue(
                f"all {len(cards)} multiple-choice cards have exactly {counts.pop()} correct "
                "options; vary the count (including 1 and all)",
                file=scope,
            )


@check("duplicates", "No two cards ask (nearly) the same question")
def duplicates(ctx: CheckContext) -> Iterator[Issue]:
    seen: list[tuple[str, CardFile, Card]] = []
    threshold = ctx.course.checks.similarity
    for cf, card in ctx.cards():
        text = _norm(card.question)
        for other_text, other_cf, other in seen:
            matcher = SequenceMatcher(None, text, other_text, autojunk=False)
            if matcher.quick_ratio() >= threshold and matcher.ratio() >= threshold:
                yield Issue(
                    f"near-duplicate of {other_cf.label}:{other.id}", file=cf.label, card=card.id
                )
                break
        seen.append((text, cf, card))


@check("answer-in-question", "The question text does not give away the answer")
def answer_in_question(ctx: CheckContext) -> Iterator[Issue]:
    for cf, card in ctx.cards():
        question = _norm(card.question)
        match card:
            case OpenCard(answer=answer):
                answers = [answer]
            case ChoiceCard():
                answers = [card.options[i] for i in card.correct_indices]
        for answer in map(_norm, answers):
            if len(answer) >= 12 and answer in question:
                yield Issue("question contains the correct answer", file=cf.label, card=card.id)
                break


@check("explanation", "Every card has an explanation")
def explanation(ctx: CheckContext) -> Iterator[Issue]:
    for cf, card in ctx.cards():
        if not card.explanation:
            yield Issue("missing explanation", file=cf.label, card=card.id)
