from collections.abc import Sequence
from dataclasses import dataclass

NAV_COOKIE = "keel_nav"
NAV_COOKIE_MAX_AGE = 400 * 24 * 60 * 60

DEFAULT_ORDER: tuple[str, ...] = (
    "projects",
    "create",
    "board",
    "backlog",
    "sprints",
    "schedules",
    "users",
)
PROJECT_ITEMS = frozenset({"board", "backlog", "sprints", "schedules"})
KNOWN = frozenset(DEFAULT_ORDER)
LABELS = {
    "projects": "Projects",
    "create": "Create",
    "board": "Board",
    "backlog": "Backlog",
    "sprints": "Sprints",
    "schedules": "Schedules",
    "users": "Users",
}


@dataclass(frozen=True)
class NavLink:
    """One reorderable section link in the top bar."""

    key: str
    label: str
    href: str
    modifier: str = ""


def known_keys(parts: Sequence[str]) -> tuple[str, ...]:
    """Unique known keys in the order given, nothing added."""
    seen: list[str] = []
    for part in parts:
        key = part.strip()
        if key in KNOWN and key not in seen:
            seen.append(key)
    return tuple(seen)


def complete(order: Sequence[str]) -> tuple[str, ...]:
    """Known keys in the given order, then any defaults that were omitted."""
    seen = list(known_keys(order))
    for key in DEFAULT_ORDER:
        if key not in seen:
            seen.append(key)
    return tuple(seen)


def parse_order(raw: str | None) -> tuple[str, ...]:
    """Known keys from a cookie, then any defaults the cookie omitted."""
    if not raw:
        return complete(())
    return complete(raw.replace(",", ".").split("."))


def encode_order(order: Sequence[str]) -> str:
    return ".".join(complete(order))


def merge_visible(full: Sequence[str], visible: Sequence[str]) -> tuple[str, ...]:
    """Replace the visible subsequence in `full` with `visible`, keeping hidden keys."""
    current = complete(full)
    shown = known_keys(visible)
    if not shown:
        return current
    shown_set = set(shown)
    queue = iter(shown)
    return tuple(next(queue) if key in shown_set else key for key in current)


def move_item(
    visible: Sequence[str],
    item: str,
    direction: str,
) -> tuple[str, ...]:
    """Swap `item` with its neighbour in the visible list. Ends are no-ops."""
    items = list(known_keys(visible))
    if item not in items:
        return tuple(items)
    index = items.index(item)
    if direction == "up":
        neighbour = index - 1
    elif direction == "down":
        neighbour = index + 1
    else:
        return tuple(items)
    if neighbour < 0 or neighbour >= len(items):
        return tuple(items)
    items[index], items[neighbour] = items[neighbour], items[index]
    return tuple(items)


def links_for(order: Sequence[str], project_key: str | None) -> list[NavLink]:
    """Section links in cookie order. Project-scoped keys need a project."""
    found: list[NavLink] = []
    for key in complete(order):
        if key in PROJECT_ITEMS and not project_key:
            continue
        found.append(
            NavLink(
                key=key,
                label=LABELS[key],
                href=_href(key, project_key),
                modifier="keel-topbar__create" if key == "create" else "",
            ),
        )
    return found


def _href(key: str, project_key: str | None) -> str:
    if key == "projects":
        return "/projects"
    if key == "create":
        return f"/create?project={project_key}" if project_key else "/create"
    if key == "board":
        return f"/projects/{project_key}/board"
    if key == "backlog":
        return f"/projects/{project_key}/backlog"
    if key == "sprints":
        return f"/projects/{project_key}/sprints"
    if key == "schedules":
        return f"/projects/{project_key}/schedules"
    return "/users"
