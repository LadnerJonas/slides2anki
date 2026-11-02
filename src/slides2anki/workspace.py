from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Self

from slides2anki.config import Course

CONFIG_NAME = "course.toml"
DEFAULT_DIR = "slides2anki"


class WorkspaceError(Exception):
    pass


@dataclass(frozen=True)
class Workspace:
    """The dedicated slides2anki folder; the lecture folder (`base`) is only ever read."""

    root: Path

    @classmethod
    def find(cls, start: Path | None = None) -> Self:
        here = (start or Path.cwd()).resolve()
        for directory in (here, *here.parents):
            for candidate in (directory, directory / DEFAULT_DIR):
                if (candidate / CONFIG_NAME).is_file():
                    return cls(candidate)
        raise WorkspaceError(
            f"No {CONFIG_NAME} found. Run `slides2anki init` in your lecture folder first."
        )

    @cached_property
    def course(self) -> Course:
        return Course.load(self.config_file)

    @cached_property
    def base(self) -> Path:
        return (self.root / self.course.sources.root).resolve()

    @property
    def config_file(self) -> Path:
        return self.root / CONFIG_NAME

    @property
    def outline_file(self) -> Path:
        return self.root / "outline.toml"

    @property
    def todo(self) -> Path:
        return self.root / "TODO.md"

    @property
    def context(self) -> Path:
        return self.root / "context"

    @property
    def cards(self) -> Path:
        return self.root / "cards"

    @property
    def checks(self) -> Path:
        return self.root / "checks"

    @property
    def decks(self) -> Path:
        return self.root / "decks"

    @property
    def cache(self) -> Path:
        return self.root / ".cache"

    @property
    def pages(self) -> Path:
        return self.cache / "pages"

    @property
    def tasks(self) -> Path:
        return self.cache / "tasks"

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def card_file(self, slug: str) -> Path:
        return self.cards / f"{slug}.json"
