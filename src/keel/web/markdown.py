"""Turn stored note text into sanitized HTML. Presentation only; source stays plain."""

from __future__ import annotations

import bleach
import markdown
from markupsafe import Markup

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


def render_markdown(text: str) -> Markup:
    """HTML for an issue description or comment; empty source stays empty."""
    if not text.strip():
        return Markup("")
    html = markdown.markdown(text, extensions=_EXTENSIONS)
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return Markup(bleach.linkify(cleaned))
