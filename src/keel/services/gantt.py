"""A timeline of dated issues, one row each."""

from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Dependency, Issue, Project
from keel.domain.enums import DependencyKind, IssueStatus
from keel.services import issues as issue_service
from keel.services.calendar import chosen_month
from keel.services.home import _calendar_day
from keel.services.issues import IssueFilters

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_SHORT = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_DOW = ("M", "T", "W", "T", "F", "S", "S")


@dataclass(frozen=True)
class GanttColumn:
    """One day on a month, or one week on a quarter."""

    mark: str
    dow: str
    hint: str
    is_today: bool


@dataclass(frozen=True)
class GanttRow:
    """One issue clipped to the days or weeks on the page."""

    key: str
    title: str
    type: str
    status: IssueStatus
    depth: int
    column: int
    length: int
    continues_before: bool
    continues_after: bool
    point: bool


@dataclass(frozen=True)
class GanttLink:
    """A dependency whose two issues are both rows on this page."""

    kind: str
    text: str
    path: str
    tip: str
    tip_x: str
    tip_y: str


@dataclass(frozen=True)
class GanttChart:
    """The month page or the quarter page."""

    label: str
    view: str
    month_number: int
    year: int
    years: tuple[int, ...]
    month_names: tuple[str, ...]
    prev_href: str
    next_href: str
    today_href: str
    month_href: str
    quarter_href: str
    columns: tuple[GanttColumn, ...]
    rows: tuple[GanttRow, ...]
    links: tuple[GanttLink, ...]
    today_column: int | None
    empty: bool
    empty_note: str
    base: str


@dataclass(frozen=True)
class _Placed:
    issue_id: int
    parent_id: int | None
    key: str
    title: str
    project_key: str
    number: int
    type: str
    status: IssueStatus
    start: date
    end: date
    column: int
    length: int
    continues_before: bool
    continues_after: bool
    depth: int = 0


def parse_view(raw: str | None) -> str:
    """`quarter` selects the quarter. Anything else is the month."""
    if raw == "quarter":
        return "quarter"
    return "month"


def open_gantt(
    session: Session,
    assignee_id: int | None = None,
    *,
    view: str | None,
    month: str | None,
    year: int | None,
    month_num: int | None,
    today: date,
    project_id: int | None = None,
    base: str = "/gantt",
    filters: IssueFilters | None = None,
) -> GanttChart:
    """Month or quarter for one person, one project, or a signed-out chart."""
    scale = parse_view(view)
    anchor = chosen_month(month, year=year, month_num=month_num, today=today)
    if scale == "quarter":
        anchor = _quarter_start(anchor)
    window_start, window_end = _bounds(anchor, scale)
    if project_id is None and assignee_id is None:
        placed: list[_Placed] = []
    else:
        placed = _load(
            session,
            assignee_id,
            project_id,
            window_start,
            window_end,
            _column_starts(scale, window_start, window_end),
            filters,
        )
    arranged = _arrange(placed)
    columns = len(_column_starts(scale, window_start, window_end))
    links = _links(session, arranged, scale, columns) if arranged else ()
    return _describe(
        anchor,
        scale,
        today,
        window_start,
        window_end,
        arranged,
        links,
        base,
    )


def _bounds(anchor: date, scale: str) -> tuple[date, date]:
    if scale == "quarter":
        start = _quarter_start(anchor)
        return start, _quarter_end(start)
    last = monthrange(anchor.year, anchor.month)[1]
    return anchor, date(anchor.year, anchor.month, last)


def _column_starts(scale: str, start: date, end: date) -> tuple[date, ...]:
    if scale == "quarter":
        return _week_starts(start, end)
    cursor = start
    days: list[date] = []
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return tuple(days)


def _week_starts(start: date, end: date) -> tuple[date, ...]:
    cursor = start - timedelta(days=start.weekday())
    last = end - timedelta(days=end.weekday())
    weeks: list[date] = []
    while cursor <= last:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return tuple(weeks)


def _load(
    session: Session,
    assignee_id: int | None,
    project_id: int | None,
    window_start: date,
    window_end: date,
    starts: Sequence[date],
    filters: IssueFilters | None,
) -> list[_Placed]:
    statement = select(Issue, Project).join(Project, Issue.project_id == Project.id)
    if project_id is not None:
        statement = statement.where(Issue.project_id == project_id)
    elif assignee_id is not None:
        statement = statement.where(Issue.assignee_id == assignee_id)
    else:
        return []
    if filters is not None:
        statement = issue_service.restrict(statement, filters)
    placed: list[_Placed] = []
    for issue, project in session.execute(statement).all():
        window = _window(issue)
        if window is None:
            continue
        start, end = window
        if end < window_start or start > window_end:
            continue
        shown_start = max(start, window_start)
        shown_end = min(end, window_end)
        first = _slot(shown_start, starts)
        last = _slot(shown_end, starts)
        placed.append(
            _Placed(
                issue_id=issue.id,
                parent_id=issue.parent_id,
                key=issue_service.issue_key(issue, project),
                title=issue.title,
                project_key=project.key,
                number=issue.number,
                type=issue.type.value,
                status=issue.status,
                start=start,
                end=end,
                column=first + 1,
                length=last - first + 1,
                continues_before=start < window_start,
                continues_after=end > window_end,
            ),
        )
    return placed


def _window(issue: Issue) -> tuple[date, date] | None:
    start = _calendar_day(issue.start_at) if issue.start_at is not None else None
    due = _calendar_day(issue.due_at) if issue.due_at is not None else None
    if start is None and due is None:
        return None
    if start is None:
        assert due is not None
        return due, due
    if due is None:
        return start, start
    return start, due


def _slot(day: date, starts: Sequence[date]) -> int:
    """Largest column whose first day is on or before `day`."""
    slot = 0
    for index, start in enumerate(starts):
        if start <= day:
            slot = index
        else:
            break
    return slot


def _arrange(items: Sequence[_Placed]) -> tuple[_Placed, ...]:
    """Parents before their children. A parent that is not on the page is a root."""
    by_id = {item.issue_id: item for item in items}
    children: dict[int | None, list[_Placed]] = {}
    for item in items:
        parent = item.parent_id if item.parent_id in by_id else None
        children.setdefault(parent, []).append(item)

    def sort_key(item: _Placed) -> tuple[date, date, str, int]:
        return (item.start, item.end, item.project_key, item.number)

    for group in children.values():
        group.sort(key=sort_key)
    ordered: list[_Placed] = []
    seen: set[int] = set()

    def walk(parent: int | None, depth: int) -> None:
        for item in children.get(parent, ()):
            if item.issue_id in seen:
                continue
            seen.add(item.issue_id)
            ordered.append(replace(item, depth=depth))
            walk(item.issue_id, depth + 1)

    walk(None, 0)
    for item in items:
        if item.issue_id not in seen:
            ordered.append(item)
    return tuple(ordered)


def _links(
    session: Session,
    placed: Sequence[_Placed],
    scale: str,
    columns: int,
) -> tuple[GanttLink, ...]:
    """Blocks and relates-to edges whose ends are both on the page."""
    by_id = {item.issue_id: item for item in placed}
    order = {item.issue_id: index for index, item in enumerate(placed)}
    if len(by_id) < 2:
        return ()
    ids = tuple(by_id)
    found = session.scalars(
        select(Dependency).where(
            Dependency.source_id.in_(ids),
            Dependency.target_id.in_(ids),
        ),
    ).all()
    links = [
        _link(row, by_id, order, scale, columns, len(placed))
        for row in found
        if row.source_id in by_id and row.target_id in by_id
    ]
    links.sort(key=lambda link: (0 if link.kind == "blocks" else 1, link.text))
    return tuple(links)


def _link(
    row: Dependency,
    by_id: dict[int, _Placed],
    order: dict[int, int],
    scale: str,
    columns: int,
    rows: int,
) -> GanttLink:
    source = by_id[row.source_id]
    target = by_id[row.target_id]
    y1 = order[source.issue_id] + 0.5
    y2 = order[target.issue_id] + 0.5
    if row.kind is DependencyKind.BLOCKS:
        points = _blocks_points(
            _anchor(source, "finish", scale),
            y1,
            _anchor(target, "start", scale),
            y2,
            columns,
            rows,
        )
        text = f"{source.key} blocks {target.key}"
        tip = _tip_direction(points)
    else:
        points = _relates_points(
            _anchor(source, "center", scale),
            y1,
            _anchor(target, "center", scale),
            y2,
        )
        text = f"{source.key} relates to {target.key}"
        tip = ""
    end_x, end_y = points[-1]
    return GanttLink(
        kind=row.kind.value,
        text=text,
        path=_path(points),
        tip=tip,
        tip_x=_pct(end_x, columns),
        tip_y=_pct(end_y, rows),
    )


def _anchor(item: _Placed, which: str, scale: str) -> float:
    """Left, right, or middle of the bar, in column units."""
    left = float(item.column - 1)
    point = scale == "month" and item.start == item.end
    if which == "finish":
        return left + 0.5 if point else left + item.length
    if which == "start":
        return left + 0.5 if point else left
    return left + 0.5 if point else left + item.length / 2


def _blocks_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    columns: int,
    rows: int,
) -> list[tuple[float, float]]:
    """Finish of the blocker to the start of the issue it blocks."""
    stub = 0.45
    if x2 >= x1 + stub:
        return _dedupe([(x1, y1), (x1 + stub, y1), (x1 + stub, y2), (x2, y2)])
    leave = min(float(columns), x1 + stub)
    toward = 0.82 if y2 >= y1 else -0.82
    lane = min(max(y1 + toward, 0.12), max(rows - 0.12, 0.12))
    if x2 >= stub:
        approach = x2 - stub
    else:
        approach = min(float(columns), x2 + stub)
    return _dedupe(
        [
            (x1, y1),
            (leave, y1),
            (leave, lane),
            (approach, lane),
            (approach, y2),
            (x2, y2),
        ],
    )


def _relates_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> list[tuple[float, float]]:
    """Join the middles, keeping the long stretch under the first bar."""
    lane = y1 + (0.42 if y2 >= y1 else -0.42)
    return _dedupe([(x1, y1), (x1, lane), (x2, lane), (x2, y2)])


def _dedupe(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    kept: list[tuple[float, float]] = []
    for point in points:
        if not kept or not _same(kept[-1], point):
            kept.append(point)
    return kept


def _same(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return abs(left[0] - right[0]) <= 0.001 and abs(left[1] - right[1]) <= 0.001


def _path(points: Sequence[tuple[float, float]]) -> str:
    parts = [f"M {_num(points[0][0])} {_num(points[0][1])}"]
    for x, y in points[1:]:
        parts.append(f"L {_num(x)} {_num(y)}")
    return " ".join(parts)


def _tip_direction(points: Sequence[tuple[float, float]]) -> str:
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    if abs(x2 - x1) >= abs(y2 - y1):
        return "right" if x2 >= x1 else "left"
    return "down" if y2 >= y1 else "up"


def _num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _pct(value: float, total: int) -> str:
    if total <= 0:
        return "0"
    return _num(value / total * 100)


def _describe(
    anchor: date,
    scale: str,
    today: date,
    window_start: date,
    window_end: date,
    placed: Sequence[_Placed],
    links: Sequence[GanttLink],
    base: str,
) -> GanttChart:
    starts = _column_starts(scale, window_start, window_end)
    today_column = None
    if window_start <= today <= window_end:
        today_column = _slot(today, starts) + 1
    columns = tuple(
        _column(scale, start, index + 1 == today_column)
        for index, start in enumerate(starts)
    )
    rows = tuple(
        GanttRow(
            key=item.key,
            title=item.title,
            type=item.type,
            status=item.status,
            depth=item.depth,
            column=item.column,
            length=item.length,
            continues_before=item.continues_before,
            continues_after=item.continues_after,
            point=scale == "month" and item.start == item.end,
        )
        for item in placed
    )
    if scale == "quarter":
        label = (
            f"{_MONTHS[window_start.month - 1]}–"
            f"{_MONTHS[window_end.month - 1]} {window_start.year}"
        )
        previous = _shift_month(window_start, -3)
        following = _shift_month(window_start, 3)
        prev_href = _quarter_href(base, previous)
        next_href = _quarter_href(base, following)
        today_href = f"{base}?view=quarter"
        month_href = _month_href(base, _month_from_quarter(window_start, today))
        quarter_href = _quarter_href(base, window_start)
        note = "Nothing dated falls in this quarter."
    else:
        label = f"{_MONTHS[anchor.month - 1]} {anchor.year}"
        prev_href = _month_href(base, _shift_month(anchor, -1))
        next_href = _month_href(base, _shift_month(anchor, 1))
        today_href = base
        month_href = _month_href(base, anchor)
        quarter_href = _quarter_href(base, anchor)
        note = "Nothing dated falls in this month."
    return GanttChart(
        label=label,
        view=scale,
        month_number=anchor.month,
        year=anchor.year,
        years=_year_choices(today, anchor),
        month_names=_MONTHS,
        prev_href=prev_href,
        next_href=next_href,
        today_href=today_href,
        month_href=month_href,
        quarter_href=quarter_href,
        columns=columns,
        rows=rows,
        links=tuple(links),
        today_column=today_column,
        empty=not rows,
        empty_note=note,
        base=base,
    )


def _column(scale: str, start: date, is_today: bool) -> GanttColumn:
    if scale == "quarter":
        return GanttColumn(
            mark=f"{_SHORT[start.month - 1]} {start.day}",
            dow="",
            hint=f"Week of {_MONTHS[start.month - 1]} {start.day}, {start.year}",
            is_today=is_today,
        )
    return GanttColumn(
        mark=str(start.day),
        dow=_DOW[start.weekday()],
        hint=(
            f"{_WEEKDAYS[start.weekday()]}, "
            f"{_MONTHS[start.month - 1]} {start.day}, {start.year}"
        ),
        is_today=is_today,
    )


def _month_from_quarter(quarter_start: date, today: date) -> date:
    end = _quarter_end(quarter_start)
    if quarter_start <= today <= end:
        return date(today.year, today.month, 1)
    return quarter_start


def _quarter_start(day: date) -> date:
    first_month = ((day.month - 1) // 3) * 3 + 1
    return date(day.year, first_month, 1)


def _quarter_end(start: date) -> date:
    last_month = start.month + 2
    return date(start.year, last_month, monthrange(start.year, last_month)[1])


def _shift_month(first: date, delta: int) -> date:
    index = first.year * 12 + (first.month - 1) + delta
    year, month_index = divmod(index, 12)
    if year < 1:
        return date(1, 1, 1)
    if year > 9999:
        return date(9999, 12, 1)
    return date(year, month_index + 1, 1)


def _year_choices(today: date, shown: date) -> tuple[int, ...]:
    start = max(1, min(today.year - 5, shown.year))
    end = min(9999, max(today.year + 5, shown.year))
    return tuple(range(start, end + 1))


def _month_href(base: str, day: date) -> str:
    return f"{base}?month={day.strftime('%Y-%m')}"


def _quarter_href(base: str, day: date) -> str:
    start = _quarter_start(day)
    return f"{base}?view=quarter&month={start.strftime('%Y-%m')}"
