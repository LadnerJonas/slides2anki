import html
import re

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table")
_MATH = re.compile(r"\\\(.+?\\\)|\\\[.+?\\\]", re.S)


def _render(text: str, render) -> str:
    spans: list[str] = []

    def stash(m: re.Match[str]) -> str:
        spans.append(html.escape(m.group(0), quote=False))
        return f"S2AMATH{len(spans) - 1}X"

    out = render(_MATH.sub(stash, text)).strip()
    return re.sub(r"S2AMATH(\d+)X", lambda m: spans[int(m.group(1))], out)


def inline(text: str) -> str:
    return _render(text, _md.renderInline)


def block(text: str) -> str:
    return _render(text, _md.render) if text else ""
