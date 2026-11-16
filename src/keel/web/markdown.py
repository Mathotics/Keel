"""Turn stored note text into sanitized HTML. Presentation only; source stays plain."""

from __future__ import annotations

import re

import bleach
import markdown
from markupsafe import Markup

_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
_QUOTE_LINE = re.compile(r"^[ ]{0,3}>")
_QUOTE_BREAK = "<!-- keel-quote-break -->"

_EXTENSIONS = ("fenced_code", "tables", "nl2br", "sane_lists")
_ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "em",
        "a",
        "ul",
        "ol",
        "li",
        "code",
        "pre",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "del",
    },
)
_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "a": ["href", "title"],
    "th": ["align"],
    "td": ["align"],
}
_ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto"})


def _separate_blockquote_gaps(text: str) -> str:
    """Keep a blank line between quotes from collapsing them into one quote.

    Python-Markdown joins ``> one`` and ``> two`` across a blank line. A marker
    between them makes two quote blocks, and the sanitizer removes the marker.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    separated: list[str] = []
    in_fence = False
    fence_mark = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = _FENCE.match(line)
        if not in_fence and fence:
            in_fence = True
            fence_mark = fence.group(2)[0]
            separated.append(line)
            index += 1
            continue
        if in_fence:
            separated.append(line)
            indented = len(line) - len(line.lstrip())
            if indented <= 3 and line.lstrip().startswith(fence_mark * 3):
                in_fence = False
            index += 1
            continue
        separated.append(line)
        if _QUOTE_LINE.match(line):
            gap = index + 1
            while gap < len(lines) and lines[gap].strip() == "":
                gap += 1
            if gap > index + 1 and gap < len(lines) and _QUOTE_LINE.match(lines[gap]):
                separated.extend(("", _QUOTE_BREAK, ""))
                index = gap
                continue
        index += 1
    return "\n".join(separated)


def render_markdown(text: str) -> Markup:
    """HTML for an issue description or comment; empty source stays empty."""
    if not text.strip():
        return Markup("")
    html = markdown.markdown(_separate_blockquote_gaps(text), extensions=_EXTENSIONS)
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return Markup(bleach.linkify(cleaned))
