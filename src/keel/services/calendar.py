"""Month calendar of the acting user's dated work."""

from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project
from keel.domain.enums import CLOSED_STATUSES
from keel.services import issues as issue_service
from keel.services.home import _calendar_day

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


@dataclass(frozen=True)
class CalendarSpan:
    """One bar clipped to a single Monday–Sunday week."""

    key: str
    title: str
    project_key: str
    type: str
    column: int
    length: int
    lane: int
    continues_before: bool
    continues_after: bool


@dataclass(frozen=True)
class CalendarDay:
    date: date
    in_month: bool
    is_today: bool


@dataclass(frozen=True)
class CalendarWeek:
    days: tuple[CalendarDay, ...]
    spans: tuple[CalendarSpan, ...]


@dataclass(frozen=True)
class MonthCalendar:
    label: str
    month: str
    month_number: int
    year: int
    years: tuple[int, ...]
    month_names: tuple[str, ...]
    prev_month: str
    next_month: str
    weeks: tuple[CalendarWeek, ...]
    empty: bool
    base: str


@dataclass(frozen=True)
class _Bar:
    key: str
    title: str
    project_key: str
    type: str
    number: int
    start: date
    end: date


def chosen_month(
    raw: str | None,
    *,
    year: int | None,
    month_num: int | None,
    today: date,
) -> date:
    """The month from the dropdowns, or from `YYYY-MM` when those are absent."""
    if year is not None and month_num is not None:
        return parse_month(f"{year}-{month_num}", today)
    return parse_month(raw, today)


def parse_month(raw: str | None, today: date) -> date:
    """First day of `YYYY-MM`, or the month containing `today` when that is unusable."""
    fallback = date(today.year, today.month, 1)
    if raw is None:
        return fallback
    parts = raw.strip().split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return fallback
    parsed_year = int(parts[0])
    parsed_month = int(parts[1])
    if parsed_year < 1 or parsed_year > 9999 or parsed_month < 1 or parsed_month > 12:
        return fallback
    return date(parsed_year, parsed_month, 1)


def month_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    month: date,
    today: date | None = None,
    project_id: int | None = None,
    base: str = "/calendar",
) -> MonthCalendar:
    """Unfinished dated issues for one person, or for one project, on one month."""
    day = today or date.today()
    first = date(month.year, month.month, 1)
    statement = select(Issue, Project).join(Project, Issue.project_id == Project.id)
    if project_id is not None:
        statement = statement.where(Issue.project_id == project_id)
    elif assignee_id is not None:
        statement = statement.where(Issue.assignee_id == assignee_id)
    else:
        return blank_month(first, today=day, base=base)
    grid_start, grid_end = _grid(first)
    found = session.execute(statement).all()
    bars: list[_Bar] = []
    for issue, project in found:
        if issue.status in CLOSED_STATUSES:
            continue
        window = _window(issue)
        if window is None:
            continue
        start, end = window
        if end < grid_start or start > grid_end:
            continue
        bars.append(
            _Bar(
                key=issue_service.issue_key(issue, project),
                title=issue.title,
                project_key=project.key,
                type=issue.type.value,
                number=issue.number,
                start=start,
                end=end,
            ),
        )
    bars.sort(key=lambda bar: (bar.start, bar.project_key, bar.number))
    return _describe(first, day, bars, base)


def blank_month(
    month: date,
    *,
    today: date | None = None,
    base: str = "/calendar",
) -> MonthCalendar:
    """The same grid with no issues, for a page that has no acting user."""
    day = today or date.today()
    return _describe(date(month.year, month.month, 1), day, (), base)


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


def _describe(
    first: date,
    today: date,
    bars: Sequence[_Bar],
    base: str,
) -> MonthCalendar:
    weeks = _weeks(first, today, bars)
    return MonthCalendar(
        label=f"{_MONTHS[first.month - 1]} {first.year}",
        month=_token(first),
        month_number=first.month,
        year=first.year,
        years=_year_choices(today, first),
        month_names=_MONTHS,
        prev_month=_token(_shift(first, -1)),
        next_month=_token(_shift(first, 1)),
        weeks=weeks,
        empty=not any(week.spans for week in weeks),
        base=base,
    )


def _year_choices(today: date, shown: date) -> tuple[int, ...]:
    start = max(1, min(today.year - 5, shown.year))
    end = min(9999, max(today.year + 5, shown.year))
    return tuple(range(start, end + 1))


def _weeks(
    first: date,
    today: date,
    bars: Sequence[_Bar],
) -> tuple[CalendarWeek, ...]:
    grid_start, grid_end = _grid(first)
    weeks: list[CalendarWeek] = []
    cursor = grid_start
    while cursor <= grid_end:
        week_end = cursor + timedelta(days=6)
        days = tuple(
            CalendarDay(
                date=cursor + timedelta(days=offset),
                in_month=(cursor + timedelta(days=offset)).year == first.year
                and (cursor + timedelta(days=offset)).month == first.month,
                is_today=cursor + timedelta(days=offset) == today,
            )
            for offset in range(7)
        )
        weeks.append(CalendarWeek(days=days, spans=_place(bars, cursor, week_end)))
        cursor += timedelta(days=7)
    return tuple(weeks)


def _grid(first: date) -> tuple[date, date]:
    last = date(first.year, first.month, monthrange(first.year, first.month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=6 - last.weekday())
    return grid_start, grid_end


def _place(
    bars: Sequence[_Bar],
    week_start: date,
    week_end: date,
) -> tuple[CalendarSpan, ...]:
    lanes: list[date] = []
    placed: list[CalendarSpan] = []
    for bar in bars:
        if bar.end < week_start or bar.start > week_end:
            continue
        shown_start = max(bar.start, week_start)
        shown_end = min(bar.end, week_end)
        lane_index: int | None = None
        for index, occupied_until in enumerate(lanes):
            if shown_start > occupied_until:
                lanes[index] = shown_end
                lane_index = index
                break
        if lane_index is None:
            lanes.append(shown_end)
            lane_index = len(lanes) - 1
        placed.append(
            CalendarSpan(
                key=bar.key,
                title=bar.title,
                project_key=bar.project_key,
                type=bar.type,
                column=(shown_start - week_start).days + 1,
                length=(shown_end - shown_start).days + 1,
                lane=lane_index + 1,
                continues_before=bar.start < week_start,
                continues_after=bar.end > week_end,
            ),
        )
    return tuple(placed)


def _shift(first: date, delta: int) -> date:
    index = first.year * 12 + (first.month - 1) + delta
    year, month_index = divmod(index, 12)
    if year < 1:
        return date(1, 1, 1)
    if year > 9999:
        return date(9999, 12, 1)
    return date(year, month_index + 1, 1)


def _token(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"
