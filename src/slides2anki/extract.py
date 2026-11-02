import hashlib
import re
from collections import Counter
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

import pypdfium2 as pdfium
from pydantic import BaseModel

from slides2anki.sources import Source, discover
from slides2anki.workspace import Workspace

RENDER_WIDTH = 1280
JPEG_QUALITY = 80


class Document(BaseModel):
    source: str
    slug: str
    sha: str
    pages: list[str]
    sparse: list[int]

    @property
    def short_sha(self) -> str:
        return self.sha[:16]


def file_sha(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def normalize(text: str) -> str:
    text = text.replace("\r", "\n").replace("\f", "\n")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def strip_chrome(pages: list[str]) -> list[str]:
    """Drop short lines repeated on most pages (headers, footers, course names)."""
    if len(pages) < 4:
        return pages
    counts = Counter(line for page in pages for line in set(page.splitlines()))
    chrome = {line for line, n in counts.items() if n >= len(pages) / 2 and len(line) < 80}
    return ["\n".join(ln for ln in p.splitlines() if ln not in chrome) for p in pages]


def pdf_pages(path: Path, image_dir: Path | None = None) -> Iterator[str]:
    pdf = pdfium.PdfDocument(path)
    try:
        for number, page in enumerate(pdf, 1):
            textpage = page.get_textpage()
            yield normalize(textpage.get_text_range())
            textpage.close()
            if image_dir:
                bitmap = page.render(scale=RENDER_WIDTH / page.get_width())
                bitmap.to_pil().convert("RGB").save(
                    image_dir / f"p{number:03}.jpg", quality=JPEG_QUALITY, optimize=True
                )
            page.close()
    finally:
        pdf.close()


def page_image(ws: Workspace, slug: str, page: int) -> Path:
    return ws.pages / slug / f"p{page:03}.jpg"


def extract_slides(ws: Workspace, src: Source) -> tuple[Document, bool]:
    """Return the cached document for a slide PDF, extracting it if new or changed."""
    out = ws.pages / src.slug
    meta = out / "document.json"
    sha = file_sha(src.path)
    if meta.is_file():
        cached = Document.model_validate_json(meta.read_text("utf-8"))
        if cached.sha == sha and cached.source == src.rel:
            return cached, False
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("p*.jpg"):
        stale.unlink()
    pages = strip_chrome(list(pdf_pages(src.path, out)))
    limit = ws.course.min_page_chars
    sparse = [i for i, text in enumerate(pages, 1) if len(text) < limit]
    doc = Document(source=src.rel, slug=src.slug, sha=sha, pages=pages, sparse=sparse)
    meta.write_text(doc.model_dump_json(indent=1), "utf-8")
    return doc, True


def load_document(ws: Workspace, slug: str) -> Document | None:
    meta = ws.pages / slug / "document.json"
    return Document.model_validate_json(meta.read_text("utf-8")) if meta.is_file() else None


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "nav", "footer", "head"}:
            self._skip += 1
        elif tag in {"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer", "head"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_text(html: str) -> str:
    parser = _TextOnly()
    parser.feed(html)
    return normalize("".join(parser.parts))


def _read_context(path: Path) -> str | None:
    match path.suffix.lower():
        case ".pdf":
            return "\n".join(pdf_pages(path))
        case ".html" | ".htm":
            return html_text(path.read_text("utf-8", errors="replace"))
        case ".md" | ".txt":
            return normalize(path.read_text("utf-8", errors="replace"))
        case _:
            return None


def context_texts(ws: Workspace) -> dict[str, str]:
    """Context files from the workspace `context/` folder and the `[sources].context` patterns."""
    own = sorted(p for p in ws.context.rglob("*") if p.is_file()) if ws.context.is_dir() else []
    out: dict[str, str] = {}
    for path in own:
        if (text := _read_context(path)) is not None:
            out[ws.rel(path)] = text
    for path in discover(ws).context:
        if (text := _read_context(path)) is not None:
            out[path.relative_to(ws.base).as_posix()] = text
    return out
