import json
from dataclasses import dataclass
from pathlib import Path
from string import ascii_uppercase
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]
Text = Annotated[str, Field(min_length=1)]
Letter = Annotated[str, Field(pattern=r"^[A-F]$")]


class _Card(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: Slug
    question: Text
    explanation: str = ""
    pages: list[PositiveInt] = Field(min_length=1)
    figure: PositiveInt | None = None
    tags: list[str] = []


class ChoiceCard(_Card):
    options: list[Text] = Field(min_length=3, max_length=6)

    @property
    def letters(self) -> str:
        return ascii_uppercase[: len(self.options)]

    @property
    def correct_indices(self) -> set[int]:
        raise NotImplementedError

    def _check_options(self, correct: list[str]) -> None:
        if bad := [c for c in correct if c not in self.letters]:
            raise ValueError(f"correct {bad} not among options {list(self.letters)}")
        if len({o.casefold() for o in self.options}) != len(self.options):
            raise ValueError("options must be distinct")


class SingleChoice(ChoiceCard):
    type: Literal["single"]
    correct: Letter

    @model_validator(mode="after")
    def _valid(self) -> Self:
        self._check_options([self.correct])
        return self

    @property
    def correct_indices(self) -> set[int]:
        return {self.letters.index(self.correct)}


class MultipleChoice(ChoiceCard):
    type: Literal["multi"]
    correct: list[Letter] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid(self) -> Self:
        if len(set(self.correct)) != len(self.correct):
            raise ValueError("correct contains duplicates")
        self._check_options(self.correct)
        return self

    @property
    def correct_indices(self) -> set[int]:
        return {self.letters.index(c) for c in self.correct}


class OpenCard(_Card):
    type: Literal["open"]
    answer: Text


type Card = Annotated[SingleChoice | MultipleChoice | OpenCard, Field(discriminator="type")]


class CardFileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Text
    source_hash: Text
    cards: list[Card]


@dataclass(frozen=True)
class CardFile:
    path: Path
    source: str
    source_hash: str
    cards: list[Card]

    @property
    def slug(self) -> str:
        return self.path.stem

    @property
    def label(self) -> str:
        return f"{self.path.parent.name}/{self.path.name}"


class CardFileError(Exception):
    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"{path.name}: {'; '.join(problems)}")
        self.path = path
        self.problems = problems


def _loc(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        elif part not in {"single", "multi", "open"}:
            out += f".{part}" if out else str(part)
    return out or "(root)"


def load_card_file(path: Path) -> CardFile:
    try:
        model = CardFileModel.model_validate_json(path.read_bytes())
    except ValidationError as e:
        problems = [f"{_loc(err['loc'])}: {err['msg']}" for err in e.errors()]
        raise CardFileError(path, problems) from None
    return CardFile(path, model.source, model.source_hash, model.cards)


def peek_source_hash(path: Path) -> str | None:
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return data.get("source_hash") if isinstance(data, dict) else None
