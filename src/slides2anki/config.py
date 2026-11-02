import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Self

import tomli_w
from pydantic import BaseModel, Field


class CardType(StrEnum):
    SINGLE = "single"
    MULTI = "multi"
    OPEN = "open"

    @property
    def label(self) -> str:
        return CARD_TYPE_LABELS[self]


CARD_TYPE_LABELS = {
    CardType.SINGLE: "Single choice: exactly one correct option",
    CardType.MULTI: "Multiple choice: select all that apply",
    CardType.OPEN: "Free text: question, flip, answer",
}


class Checks(BaseModel):
    enabled: list[str] = []
    alpha: float = Field(0.01, gt=0, lt=1)
    similarity: float = Field(0.9, gt=0, le=1)


class Labels(BaseModel):
    single: str = "Select one"
    multi: str = "Select all that apply"


class Course(BaseModel):
    name: str
    language: str
    card_types: list[CardType] = Field(min_length=1)
    style: str = ""
    audience: str = ""
    exam: str = ""
    review_rules: list[str] = []
    min_page_chars: int = 30
    labels: Labels = Labels()
    checks: Checks = Checks()

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate(tomllib.loads(path.read_text("utf-8")))

    def save(self, path: Path) -> None:
        path.write_text(tomli_w.dumps(self.model_dump(mode="json")), "utf-8")
