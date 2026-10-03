"""Month and week calendars of dated work."""

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
_MONTHS_SHORT = (
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
    mark: str = ""


@dataclass(frozen=True)
class CalendarWeek:
    days: tuple[CalendarDay, ...]
    spans: tuple[CalendarSpan, ...]


@dataclass(frozen=True)
class MonthCalendar:
    """The month page or the week page."""

    label: str
    view: str
    month: str
    month_number: int
    year: int
    years: tuple[int, ...]
    month_names: tuple[str, ...]
    prev_month: str
    next_month: str
    prev_href: str
    next_href: str
    today_href: str
    month_href: str
    week_href: str
    weeks: tuple[CalendarWeek, ...]
    empty: bool
    empty_note: str
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


def chosen_week(
    raw: str | None,
    *,
    year: int | None,
    month_num: int | None,
    today: date,
) -> date:
    """The day that selects a week. Dropdowns win, then `YYYY-MM-DD`, else today."""
    if year is not None and month_num is not None:
        return parse_month(f"{year}-{month_num}", today)
    return parse_day(raw, today)


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


def parse_day(raw: str | None, today: date) -> date:
    """A `YYYY-MM-DD`, or `today` when that is unusable."""
    if raw is None:
        return today
    parts = raw.strip().split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return today
    parsed_year, parsed_month, parsed_day = (int(part) for part in parts)
    try:
        return date(parsed_year, parsed_month, parsed_day)
    except ValueError:
        return today


def open_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    view: str | None,
    month: str | None,
    week: str | None,
    year: int | None,
    month_num: int | None,
    today: date,
    project_id: int | None = None,
    base: str = "/calendar",
) -> MonthCalendar:
    """The month or week page for one person, one project, or a signed-out grid."""
    if view == "week":
        focus = chosen_week(week, year=year, month_num=month_num, today=today)
        if project_id is None and assignee_id is None:
            return blank_week(focus, today=today, base=base)
        return week_calendar(
            session,
            assignee_id,
            focus=focus,
            today=today,
            project_id=project_id,
            base=base,
        )
    first = chosen_month(month, year=year, month_num=month_num, today=today)
    if project_id is None and assignee_id is None:
        return blank_month(first, today=today, base=base)
    return month_calendar(
        session,
        assignee_id,
        month=first,
        today=today,
        project_id=project_id,
        base=base,
    )


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
    grid_start, grid_end = _grid(first)
    bars = _bars(session, assignee_id, project_id, grid_start, grid_end)
    if bars is None:
        return blank_month(first, today=day, base=base)
    return _describe_month(first, day, bars, base)


def week_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    focus: date,
    today: date | None = None,
    project_id: int | None = None,
    base: str = "/calendar",
) -> MonthCalendar:
    """Unfinished dated issues for one person, or for one project, on one week."""
    day = today or date.today()
    monday = _monday(focus)
    bars = _bars(session, assignee_id, project_id, monday, monday + timedelta(days=6))
    if bars is None:
        return blank_week(focus, today=day, base=base)
    return _describe_week(focus, day, bars, base)


def blank_month(
    month: date,
    *,
    today: date | None = None,
    base: str = "/calendar",
) -> MonthCalendar:
    """The same month grid with no issues, for a page that has no acting user."""
    day = today or date.today()
    return _describe_month(date(month.year, month.month, 1), day, (), base)


def blank_week(
    focus: date,
    *,
    today: date | None = None,
    base: str = "/calendar",
) -> MonthCalendar:
    """The same week with no issues, for a page that has no acting user."""
    day = today or date.today()
    return _describe_week(focus, day, (), base)


def _bars(
    session: Session,
    assignee_id: int | None,
    project_id: int | None,
    start: date,
    end: date,
) -> list[_Bar] | None:
    statement = select(Issue, Project).join(Project, Issue.project_id == Project.id)
    if project_id is not None:
        statement = statement.where(Issue.project_id == project_id)
    elif assignee_id is not None:
        statement = statement.where(Issue.assignee_id == assignee_id)
    else:
        return None
    found = session.execute(statement).all()
    bars: list[_Bar] = []
    for issue, project in found:
        if issue.status in CLOSED_STATUSES:
            continue
        window = _window(issue)
        if window is None:
            continue
        bar_start, bar_end = window
        if bar_end < start or bar_start > end:
            continue
        bars.append(
            _Bar(
                key=issue_service.issue_key(issue, project),
                title=issue.title,
                project_key=project.key,
                type=issue.type.value,
                number=issue.number,
                start=bar_start,
                end=bar_end,
            ),
        )
    bars.sort(key=lambda bar: (bar.start, bar.project_key, bar.number))
    return bars


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


def _describe_month(
    first: date,
    today: date,
    bars: Sequence[_Bar],
    base: str,
) -> MonthCalendar:
    weeks = _weeks(first, today, bars)
    anchor = _week_anchor(first, today)
    return MonthCalendar(
        label=f"{_MONTHS[first.month - 1]} {first.year}",
        view="month",
        month=_token(first),
        month_number=first.month,
        year=first.year,
        years=_year_choices(today, first),
        month_names=_MONTHS,
        prev_month=_token(_shift(first, -1)),
        next_month=_token(_shift(first, 1)),
        prev_href=f"{base}?month={_token(_shift(first, -1))}",
        next_href=f"{base}?month={_token(_shift(first, 1))}",
        today_href=base,
        month_href=f"{base}?month={_token(first)}",
        week_href=f"{base}?view=week&week={anchor.isoformat()}",
        weeks=weeks,
        empty=not any(week.spans for week in weeks),
        empty_note="Nothing dated falls in this month.",
        base=base,
    )


def _describe_week(
    focus: date,
    today: date,
    bars: Sequence[_Bar],
    base: str,
) -> MonthCalendar:
    monday = _monday(focus)
    previous = _shift_week(monday, -1)
    following = _shift_week(monday, 1)
    week = CalendarWeek(
        days=_days(monday, today, month=None, mark_edges=True),
        spans=_place(bars, monday, monday + timedelta(days=6)),
    )
    return MonthCalendar(
        label=_week_label(monday),
        view="week",
        month=_token(focus),
        month_number=focus.month,
        year=focus.year,
        years=_year_choices(today, focus),
        month_names=_MONTHS,
        prev_month=previous.isoformat(),
        next_month=following.isoformat(),
        prev_href=f"{base}?view=week&week={previous.isoformat()}",
        next_href=f"{base}?view=week&week={following.isoformat()}",
        today_href=f"{base}?view=week",
        month_href=f"{base}?month={_token(focus)}",
        week_href=f"{base}?view=week&week={focus.isoformat()}",
        weeks=(week,),
        empty=not week.spans,
        empty_note="Nothing dated falls in this week.",
        base=base,
    )


def _week_label(monday: date) -> str:
    sunday = monday + timedelta(days=6)
    start = f"{_MONTHS[monday.month - 1]} {monday.day}"
    end = f"{_MONTHS[sunday.month - 1]} {sunday.day}"
    if monday.year != sunday.year:
        return f"{start}, {monday.year} – {end}, {sunday.year}"
    if monday.month != sunday.month:
        return f"{start} – {end}, {monday.year}"
    return f"{_MONTHS[monday.month - 1]} {monday.day}–{sunday.day}, {monday.year}"


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
        weeks.append(
            CalendarWeek(
                days=_days(cursor, today, month=first, mark_edges=False),
                spans=_place(bars, cursor, week_end),
            ),
        )
        cursor += timedelta(days=7)
    return tuple(weeks)


def _days(
    start: date,
    today: date,
    *,
    month: date | None,
    mark_edges: bool,
) -> tuple[CalendarDay, ...]:
    days: list[CalendarDay] = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        mark = ""
        if mark_edges and (offset == 0 or day.day == 1):
            mark = _MONTHS_SHORT[day.month - 1]
        in_month = True
        if month is not None:
            in_month = day.year == month.year and day.month == month.month
        days.append(
            CalendarDay(
                date=day,
                in_month=in_month,
                is_today=day == today,
                mark=mark,
            ),
        )
    return tuple(days)


def _grid(first: date) -> tuple[date, date]:
    last = date(first.year, first.month, monthrange(first.year, first.month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=6 - last.weekday())
    return grid_start, grid_end


def _week_anchor(first: date, today: date) -> date:
    last = date(first.year, first.month, monthrange(first.year, first.month)[1])
    if first <= today <= last:
        return today
    return first


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


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _shift(first: date, delta: int) -> date:
    index = first.year * 12 + (first.month - 1) + delta
    year, month_index = divmod(index, 12)
    if year < 1:
        return date(1, 1, 1)
    if year > 9999:
        return date(9999, 12, 1)
    return date(year, month_index + 1, 1)


def _shift_week(monday: date, delta: int) -> date:
    try:
        shifted = monday + timedelta(days=7 * delta)
    except OverflowError:
        return monday
    if shifted < date(1, 1, 1):
        return date(1, 1, 1)
    return shifted


def _token(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"
