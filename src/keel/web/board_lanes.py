"""Collapsed and hidden Kanban sprint rows (cookies, not a user row)."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

COLLAPSED_COOKIE = "keel_board_lanes"
HIDDEN_COOKIE = "keel_board_hidden"
COOKIE_MAX_AGE = 400 * 24 * 60 * 60

UNSCHEDULED = "unscheduled"
_MAX_KEYS = 200
_SPRINT = re.compile(r"[1-9]\d{0,17}")
_UNSCHEDULED = re.compile(r"unscheduled(?:-[1-9]\d{0,17})?")


@dataclass(frozen=True)
class BoardLanes:
    """Which sprint rows this browser has folded, and which it has removed."""

    collapsed: frozenset[str]
    hidden: frozenset[str]


def lane_key(sprint_id: int | None, *, project_id: int | None) -> str:
    """Stable cookie key for one sprint row.

    A sprint id is the same row on a project board and the master board.
    Unscheduled is one row per project board, and a separate row on `/board`.
    """
    if sprint_id is not None:
        return str(sprint_id)
    if project_id is None:
        return UNSCHEDULED
    return f"{UNSCHEDULED}-{project_id}"


def parse_lanes(collapsed: str | None, hidden: str | None) -> BoardLanes:
    """Known keys from the two cookies. Blank means every row is open and shown."""
    return BoardLanes(parse_keys(collapsed), parse_keys(hidden))


def parse_keys(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(_known(raw))


def encode_keys(keys: Iterable[str]) -> str:
    return ".".join(_sort(_known_from(keys)))


def encode_toggle(collapsed: Iterable[str], key: str) -> str:
    """Collapsed cookie after opening or closing one row."""
    current = set(parse_keys(encode_keys(collapsed)))
    if key in current:
        current.remove(key)
    elif _valid(key):
        current.add(key)
    return encode_keys(current)


def merge_collapsed(
    collapsed: Iterable[str],
    posted: str | None,
    present: str | None,
) -> frozenset[str]:
    """Replace the collapsed set, keeping rows that are not on this page.

    A missing `present` means the post already carries the full set, which is
    what the no-JavaScript Minimize control sends.
    """
    closed = parse_keys(posted)
    if present is None:
        return closed
    on_page = parse_keys(present)
    kept = {key for key in parse_keys(encode_keys(collapsed)) if key not in on_page}
    return frozenset(kept | {key for key in closed if key in on_page})


def hide_lane(hidden: Iterable[str], key: str) -> frozenset[str]:
    current = set(parse_keys(encode_keys(hidden)))
    if _valid(key):
        current.add(key)
    return frozenset(current)


def show_lane(hidden: Iterable[str], key: str) -> frozenset[str]:
    current = set(parse_keys(encode_keys(hidden)))
    current.discard(key)
    return frozenset(current)


def _known(raw: str) -> tuple[str, ...]:
    found: list[str] = []
    for part in raw.replace(",", ".").split("."):
        key = part.strip()
        if _valid(key) and key not in found:
            found.append(key)
        if len(found) >= _MAX_KEYS:
            break
    return tuple(found)


def _known_from(keys: Iterable[str]) -> tuple[str, ...]:
    return _known(".".join(keys))


def _valid(key: str) -> bool:
    return _SPRINT.fullmatch(key) is not None or _UNSCHEDULED.fullmatch(key) is not None


def _sort(keys: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(keys), key=_rank))


def _rank(key: str) -> tuple[int, int, str]:
    if key.isdigit():
        return (0, int(key), "")
    if key == UNSCHEDULED:
        return (1, 0, "")
    _prefix, _dash, rest = key.partition("-")
    return (2, int(rest), "")
