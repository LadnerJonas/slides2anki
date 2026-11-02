import hashlib
import os
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath

from slides2anki.workspace import Workspace

SLUG_CHARS = 60
CONTEXT_SUFFIXES = {".pdf", ".html", ".htm", ".md", ".txt"}
SKIP_DIRS = {"__MACOSX", "node_modules", "__pycache__"}


@dataclass(frozen=True)
class Source:
    path: Path
    rel: str
    slug: str


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


@cache
def glob_regex(pattern: str) -> re.Pattern[str]:
    """Case-insensitive glob on posix paths: `*` and `?` stay in one folder, `**` spans any."""
    parts = pattern.strip("/").split("/")
    regex = ""
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part == "**":
            regex += ".*" if last else "(?:[^/]+/)*"
            continue
        regex += "".join(
            "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in part
        )
        regex += "" if last else "/"
    return re.compile(regex, re.IGNORECASE)


def matches(rel: str, patterns: Iterable[str]) -> bool:
    return any(glob_regex(p).fullmatch(rel) for p in patterns)


def walk(base: Path, skip: Path | None = None) -> Iterator[str]:
    """Yield posix paths of all files below `base`, skipping hidden, saved-page and `skip` dirs."""
    skip = skip.resolve() if skip else None
    for directory, dirs, names in os.walk(base):
        here = Path(directory)
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and not d.endswith("_files")
            and d not in SKIP_DIRS
            and (here / d).resolve() != skip
        )
        for name in sorted(names):
            if not name.startswith((".", "~$")):
                yield (here / name).relative_to(base).as_posix()


def _slugs(rels: list[str]) -> dict[str, str]:
    def short(rel: str) -> str:
        return slugify(str(PurePosixPath(rel).with_suffix("")))[:SLUG_CHARS].strip("-")

    counts = Counter(short(r) for r in rels)
    return {
        r: short(r)
        if counts[short(r)] == 1 and len(short(r)) < SLUG_CHARS
        else f"{short(r)}-{hashlib.sha1(r.encode()).hexdigest()[:6]}"
        for r in rels
    }


@dataclass(frozen=True)
class Discovery:
    slides: list[Source]
    context: list[Path]
    ignored: list[str]


def discover(ws: Workspace) -> Discovery:
    sources = ws.course.sources
    slides: list[str] = []
    context: list[Path] = []
    ignored: list[str] = []
    for rel in walk(ws.base, ws.root):
        if matches(rel, sources.exclude):
            continue
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix in CONTEXT_SUFFIXES and matches(rel, sources.context):
            context.append(ws.base / rel)
        elif suffix == ".pdf" and matches(rel, sources.slides):
            slides.append(rel)
        elif suffix == ".pdf":
            ignored.append(rel)
    slugs = _slugs(slides)
    return Discovery([Source(ws.base / r, r, slugs[r]) for r in slides], context, ignored)


@dataclass(frozen=True)
class Group:
    label: str
    pattern: str
    count: int


def folder_groups(rels: list[str]) -> list[Group]:
    """Group PDFs by the first folder level below the folder they all share."""
    parents = [PurePosixPath(r).parent.parts for r in rels]
    common: tuple[str, ...] = ()
    for level in zip(*parents, strict=False):
        if len(set(level)) > 1:
            break
        common += (level[0],)
    prefix = "".join(f"{p}/" for p in common)
    counts = Counter(parts[len(common)] if len(parts) > len(common) else "" for parts in parents)
    return [
        Group(f"{prefix}{name}/", f"{prefix}{name}/**/*.pdf", n)
        if name
        else Group(f"{prefix or './'} (loose files)", f"{prefix}*.pdf", n)
        for name, n in sorted(counts.items(), key=lambda kv: (kv[0] == "", kv[0].casefold()))
    ]


def context_candidates(rels: Iterable[str]) -> list[str]:
    return [r for r in rels if PurePosixPath(r).suffix.lower() in CONTEXT_SUFFIXES - {".pdf"}]
