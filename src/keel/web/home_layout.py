"""Which home panels are shown, and in what order (cookie, not a user row)."""

from collections.abc import Sequence
from dataclasses import dataclass

from keel.services.home import HomeInbox, HomeRow
from keel.web.inbox import KNOWN, SECTIONS

HOME_COOKIE = "keel_home"
HOME_COOKIE_MAX_AGE = 400 * 24 * 60 * 60

# key, heading, extra column (due, sprint, occurrence, completed, or none)
PANELS: tuple[tuple[str, str, str | None], ...] = (
    ("due", "Due or overdue", "due"),
    ("week", "Due this week", "due"),
    ("month", "Due this month", "due"),
    ("starting", "Starting or started", None),
    ("assigned", "Assigned to me", None),
    ("blocked", "Blocked", None),
    ("sprint", "In the active sprint", "sprint"),
    ("waiting", "Waiting this cycle", "occurrence"),
    ("completed", "Completed today", "completed"),
)
TITLES = {key: title for key, title, _extra in PANELS}
EXTRAS = {key: extra for key, _title, extra in PANELS}


@dataclass(frozen=True)
class HomeLayout:
    """Enabled panels in display order, plus the ones the browser removed."""

    order: tuple[str, ...]
    hidden: frozenset[str]


def default_layout() -> HomeLayout:
    return HomeLayout(SECTIONS, frozenset())


def parse_layout(raw: str | None) -> HomeLayout:
    """Enabled order and hidden keys. A missing cookie is the default stack."""
    if not raw:
        return default_layout()
    left, _slash, right = raw.partition("/")
    hidden = frozenset(_known(right))
    order = [key for key in _known(left) if key not in hidden]
    seen = set(order)
    for key in SECTIONS:
        if key not in seen and key not in hidden:
            order.append(key)
    return HomeLayout(tuple(order), hidden)


def encode_layout(layout: HomeLayout) -> str:
    hidden = frozenset(key for key in layout.hidden if key in KNOWN)
    order = [key for key in layout.order if key in KNOWN and key not in hidden]
    seen = set(order)
    for key in SECTIONS:
        if key not in seen and key not in hidden:
            order.append(key)
    hidden_keys = [key for key in SECTIONS if key in hidden]
    return f"{'.'.join(order)}/{'.'.join(hidden_keys)}"


def hide_panel(layout: HomeLayout, key: str) -> HomeLayout:
    if key not in KNOWN or key in layout.hidden:
        return layout
    return HomeLayout(
        tuple(item for item in layout.order if item != key),
        layout.hidden | {key},
    )


def show_panel(layout: HomeLayout, key: str) -> HomeLayout:
    """Put a removed panel back at the end of the stack."""
    if key not in KNOWN or key not in layout.hidden:
        return layout
    order = tuple(item for item in layout.order if item != key)
    return HomeLayout(order + (key,), layout.hidden - {key})


def apply_move(
    layout: HomeLayout,
    visible: Sequence[str],
    item: str,
    direction: str,
) -> HomeLayout:
    """Swap `item` with its neighbour among the panels on the page."""
    items = _on_page(layout, visible)
    if item not in items:
        return layout
    index = items.index(item)
    if direction == "up":
        neighbour = index - 1
    elif direction == "down":
        neighbour = index + 1
    else:
        return layout
    if neighbour < 0 or neighbour >= len(items):
        return layout
    items[index], items[neighbour] = items[neighbour], items[index]
    return HomeLayout(_merge(layout.order, items), layout.hidden)


def apply_posted_order(layout: HomeLayout, visible: Sequence[str]) -> HomeLayout:
    """Replace the on-page subsequence, leaving empty panels where they were."""
    items = _on_page(layout, visible)
    if not items:
        return layout
    return HomeLayout(_merge(layout.order, items), layout.hidden)


def section_rows(inbox: HomeInbox, key: str) -> tuple[HomeRow, ...]:
    rows = {
        "due": inbox.due,
        "week": inbox.due_week,
        "month": inbox.due_month,
        "starting": inbox.starting,
        "assigned": inbox.assigned,
        "blocked": inbox.blocked,
        "sprint": inbox.active_sprint,
        "waiting": inbox.waiting,
        "completed": inbox.completed,
    }
    return rows[key]


def _known(raw: str) -> tuple[str, ...]:
    found: list[str] = []
    for part in raw.replace(",", ".").split("."):
        key = part.strip()
        if key in KNOWN and key not in found:
            found.append(key)
    return tuple(found)


def _on_page(layout: HomeLayout, visible: Sequence[str]) -> list[str]:
    found: list[str] = []
    for part in visible:
        key = part.strip()
        if key in KNOWN and key not in layout.hidden and key not in found:
            found.append(key)
    return found


def _merge(full: Sequence[str], visible: Sequence[str]) -> tuple[str, ...]:
    """Reorder keys already in `full`. Empty panels stay in their slots."""
    current = [key for key in full if key in KNOWN]
    shown = [key for key in visible if key in current]
    if not shown:
        return tuple(current)
    shown_set = set(shown)
    queue = iter(shown)
    return tuple(next(queue) if key in shown_set else key for key in current)
