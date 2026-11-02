import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


class Topic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    files: list[str] = []


class Outline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: list[Topic] = []

    @classmethod
    def load(cls, path: Path) -> Self:
        if not path.is_file():
            return cls()
        return cls.model_validate(tomllib.loads(path.read_text("utf-8")))

    def topic_of(self, source: str) -> tuple[int, Topic] | None:
        for number, topic in enumerate(self.topics, 1):
            if source in topic.files:
                return number, topic
        return None

    def deck_name(self, course: str, source: str) -> str:
        match self.topic_of(source):
            case (number, topic):
                return f"{course}::{number:02} {topic.title}"
            case None:
                return f"{course}::Unsorted"

    def unassigned(self, sources: list[str]) -> list[str]:
        return [s for s in sources if self.topic_of(s) is None]

    def missing(self, sources: list[str]) -> list[str]:
        known = set(sources)
        return [f for t in self.topics for f in t.files if f not in known]
