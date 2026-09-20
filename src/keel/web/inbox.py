"""Collapsed home-inbox sections (cookie, not a user row)."""

from collections.abc import Iterable

INBOX_COOKIE = "keel_inbox"
INBOX_COOKIE_MAX_AGE = 400 * 24 * 60 * 60

SECTIONS: tuple[str, ...] = (
    "due",
    "upcoming",
    "starting",
    "assigned",
    "blocked",
    "sprint",
    "waiting",
    "completed",
)
KNOWN = frozenset(SECTIONS)


def known_keys(parts: Iterable[str]) -> tuple[str, ...]:
    """Unique known section keys in canonical order."""
    selected = {part.strip() for part in parts if part.strip() in KNOWN}
    return tuple(key for key in SECTIONS if key in selected)


def parse_collapsed(raw: str | None) -> frozenset[str]:
    """Known collapsed keys from a cookie; blank means every section is open."""
    if not raw:
        return frozenset()
    return frozenset(known_keys(raw.replace(",", ".").split(".")))


def encode_collapsed(keys: Iterable[str]) -> str:
    return ".".join(known_keys(keys))


def encode_toggle(collapsed: Iterable[str], key: str) -> str:
    """Cookie value after opening or closing one section."""
    current = set(known_keys(collapsed))
    if key in current:
        current.remove(key)
    elif key in KNOWN:
        current.add(key)
    return encode_collapsed(current)
