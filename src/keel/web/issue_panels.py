"""Collapsed issue-page panels (cookie, not a user row)."""

from collections.abc import Iterable

ISSUE_PANELS_COOKIE = "keel_issue_panels"
ISSUE_PANELS_COOKIE_MAX_AGE = 400 * 24 * 60 * 60

PANELS: tuple[str, ...] = (
    "description",
    "children",
    "dependencies",
    "history",
    "comments",
)
KNOWN = frozenset(PANELS)


def known_keys(parts: Iterable[str]) -> tuple[str, ...]:
    """Unique known panel keys in canonical order."""
    selected = {part.strip() for part in parts if part.strip() in KNOWN}
    return tuple(key for key in PANELS if key in selected)


def parse_collapsed(raw: str | None) -> frozenset[str]:
    """Known collapsed keys from a cookie; blank means every panel is open."""
    if not raw:
        return frozenset()
    return frozenset(known_keys(raw.replace(",", ".").split(".")))


def encode_collapsed(keys: Iterable[str]) -> str:
    return ".".join(known_keys(keys))


def encode_toggle(collapsed: Iterable[str], key: str) -> str:
    """Cookie value after opening or closing one panel."""
    current = set(known_keys(collapsed))
    if key in current:
        current.remove(key)
    elif key in KNOWN:
        current.add(key)
    return encode_collapsed(current)
