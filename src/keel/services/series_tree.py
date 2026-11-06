"""Child recipes on a schedule. The series row stays the root."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Series, SeriesItem
from keel.domain.enums import INITIAL_PRIORITY, IssuePriority, IssueType
from keel.domain.hierarchy import PARENT_TYPE, check_children
from keel.domain.schedule import check_recipe_window, complete_offset_pair
from keel.services import labels as label_service

MAX_TITLE_LENGTH = 300


@dataclass(frozen=True)
class ItemDraft:
    title: str
    type: IssueType
    description: str = ""
    priority: IssuePriority = INITIAL_PRIORITY
    assignee_id: int | None = None
    labels: tuple[str, ...] = ()
    start_offset_days: int | None = None
    start_minute_of_day: int | None = None
    due_offset_days: int | None = None
    due_minute_of_day: int | None = None
    item_id: int | None = None
    key: str = ""
    parent_key: str | None = None


def active_items(session: Session, series_id: int) -> list[SeriesItem]:
    rows = session.scalars(
        select(SeriesItem)
        .where(SeriesItem.series_id == series_id, SeriesItem.removed.is_(False))
        .order_by(SeriesItem.position, SeriesItem.id),
    ).all()
    return spawn_order(list(rows))


def item_titles(session: Session, item_ids: Sequence[int]) -> dict[int, str]:
    wanted = [item_id for item_id in item_ids if item_id is not None]
    if not wanted:
        return {}
    rows = session.scalars(select(SeriesItem).where(SeriesItem.id.in_(wanted))).all()
    return {item.id: item.title for item in rows}


def get_item(session: Session, item_id: int) -> SeriesItem | None:
    return session.get(SeriesItem, item_id)


def replace_items(
    session: Session,
    series: Series,
    drafts: Sequence[ItemDraft],
) -> list[SeriesItem]:
    """Save the template tree. Issues that already exist are left alone."""
    existing = {
        item.id: item
        for item in session.scalars(
            select(SeriesItem).where(
                SeriesItem.series_id == series.id,
                SeriesItem.removed.is_(False),
            ),
        ).all()
    }
    seen: set[int] = set()
    rows: list[tuple[ItemDraft, SeriesItem]] = []
    for position, draft in enumerate(drafts):
        start_days, start_minute = complete_offset_pair(
            draft.start_offset_days,
            draft.start_minute_of_day,
        )
        due_days, due_minute = complete_offset_pair(
            draft.due_offset_days,
            draft.due_minute_of_day,
        )
        check_recipe_window(start_days, start_minute, due_days, due_minute)
        title = _clean_title(draft.title)
        if draft.item_id is not None:
            item = existing.get(draft.item_id)
            if item is None:
                from keel.domain.errors import InvalidSeriesError

                raise InvalidSeriesError(
                    "That schedule item is not on this schedule.",
                )
            item.title = title
            item.description = draft.description.strip()
            item.type = draft.type
            item.priority = draft.priority
            item.assignee_id = draft.assignee_id
            item.start_offset_days = start_days
            item.start_minute_of_day = start_minute
            item.due_offset_days = due_days
            item.due_minute_of_day = due_minute
            seen.add(item.id)
        else:
            item = SeriesItem(
                series_id=series.id,
                parent_item_id=None,
                position=position,
                title=title,
                description=draft.description.strip(),
                type=draft.type,
                priority=draft.priority,
                assignee_id=draft.assignee_id,
                start_offset_days=start_days,
                start_minute_of_day=start_minute,
                due_offset_days=due_days,
                due_minute_of_day=due_minute,
            )
            session.add(item)
            session.flush()
        item.position = position
        label_service.set_series_item_labels(session, item.id, draft.labels)
        rows.append((draft, item))
    _link_parents(series, rows)
    for item_id, item in existing.items():
        if item_id not in seen:
            item.removed = True
    session.flush()
    return [item for _draft, item in rows]


def seed_descendants(
    session: Session,
    series: Series,
    root: Issue,
    occurrence: date,
) -> None:
    """Copy issues already under the seed into the template and keep them."""
    from keel.domain.schedule import offsets_for_window
    from keel.services import issues as issue_service

    position = 0

    def walk(
        parent_issue: Issue,
        parent_item_id: int | None,
        parent_type: IssueType,
    ) -> None:
        nonlocal position
        for child in issue_service.list_children(session, parent_issue.id):
            if child.series_id is not None:
                from keel.domain.errors import InvalidSeriesError

                raise InvalidSeriesError(
                    "An issue under it already belongs to a schedule.",
                )
            _require_child(child.type, parent_type)
            start_days, start_minute, due_days, due_minute = offsets_for_window(
                occurrence,
                child.start_at,
                child.due_at,
            )
            item = SeriesItem(
                series_id=series.id,
                parent_item_id=parent_item_id,
                position=position,
                title=child.title,
                description=child.description,
                type=child.type,
                priority=child.priority,
                assignee_id=child.assignee_id,
                start_offset_days=start_days,
                start_minute_of_day=start_minute,
                due_offset_days=due_days,
                due_minute_of_day=due_minute,
            )
            session.add(item)
            session.flush()
            label_service.set_series_item_labels(
                session,
                item.id,
                label_service.names_for_issue(session, child.id),
            )
            child.series_id = series.id
            child.series_item_id = item.id
            child.occurrence_on = occurrence
            child.former_series_title = None
            child.former_series_cadence = None
            position += 1
            walk(child, item.id, child.type)

    walk(root, None, series.type)
    session.flush()


def spawn_order(items: Sequence[SeriesItem]) -> list[SeriesItem]:
    grouped: dict[int | None, list[SeriesItem]] = defaultdict(list)
    for item in items:
        grouped[item.parent_item_id].append(item)
    for group in grouped.values():
        group.sort(key=lambda item: (item.position, item.id))
    ordered: list[SeriesItem] = []

    def walk(parent_id: int | None) -> None:
        for item in grouped.get(parent_id, []):
            ordered.append(item)
            walk(item.id)

    walk(None)
    if len(ordered) != len(items):
        from keel.domain.errors import InvalidSeriesError

        raise InvalidSeriesError("The schedule tree could not be read.")
    return ordered


def descendant_ids(session: Session, item: SeriesItem) -> set[int]:
    rows = session.scalars(
        select(SeriesItem).where(
            SeriesItem.series_id == item.series_id,
            SeriesItem.removed.is_(False),
        ),
    ).all()
    children: dict[int | None, list[int]] = defaultdict(list)
    for row in rows:
        children[row.parent_item_id].append(row.id)
    found = {item.id}
    stack = [item.id]
    while stack:
        current = stack.pop()
        for child_id in children.get(current, []):
            if child_id not in found:
                found.add(child_id)
                stack.append(child_id)
    return found


def require_child(child: IssueType, parent: IssueType) -> None:
    _require_child(child, parent)


def assert_children_of(
    parent_type: IssueType,
    child_types: Sequence[IssueType],
) -> None:
    check_children(parent_type, child_types)


def _link_parents(series: Series, rows: list[tuple[ItemDraft, SeriesItem]]) -> None:
    from keel.domain.errors import InvalidSeriesError

    by_key: dict[str, SeriesItem] = {}
    for draft, item in rows:
        key = draft.key.strip() or f"id:{item.id}"
        if key in by_key:
            raise InvalidSeriesError("Each schedule item needs its own key.")
        by_key[key] = item
        by_key[f"id:{item.id}"] = item
    for draft, item in rows:
        parent_key = (draft.parent_key or "").strip()
        if parent_key in ("", "root"):
            item.parent_item_id = None
            continue
        parent = by_key.get(parent_key)
        if parent is None or parent.id == item.id:
            raise InvalidSeriesError("Choose a parent in this schedule.")
        item.parent_item_id = parent.id
    _assert_acyclic([item for _draft, item in rows])
    by_id = {item.id: item for _draft, item in rows}
    for _draft, item in rows:
        if item.parent_item_id is None:
            parent_type = series.type
        else:
            parent = by_id.get(item.parent_item_id)
            if parent is None:
                raise InvalidSeriesError("Choose a parent in this schedule.")
            parent_type = parent.type
        _require_child(item.type, parent_type)
    children: dict[int, list[IssueType]] = defaultdict(list)
    for _draft, item in rows:
        if item.parent_item_id is not None:
            children[item.parent_item_id].append(item.type)
    for _draft, item in rows:
        check_children(item.type, children.get(item.id, []))


def _assert_acyclic(items: Sequence[SeriesItem]) -> None:
    from keel.domain.errors import InvalidSeriesError

    by_id = {item.id: item for item in items}
    for item in items:
        seen: set[int] = set()
        current: SeriesItem | None = item
        while current is not None and current.parent_item_id is not None:
            if current.id in seen:
                raise InvalidSeriesError("A schedule item cannot contain itself.")
            seen.add(current.id)
            current = by_id.get(current.parent_item_id)
            if current is None:
                break


def _require_child(child: IssueType, parent: IssueType) -> None:
    from keel.domain.errors import InvalidSeriesError

    expected = PARENT_TYPE[child]
    if expected is None:
        raise InvalidSeriesError(f"An {child.value} never has a parent.")
    if parent is not expected:
        raise InvalidSeriesError(
            f"A {child.value} may only sit under a {expected.value}.",
        )


def _clean_title(title: str) -> str:
    from keel.domain.errors import InvalidSeriesError

    cleaned = title.strip()
    if not cleaned:
        raise InvalidSeriesError("Each item needs a title.")
    return cleaned[:MAX_TITLE_LENGTH]
