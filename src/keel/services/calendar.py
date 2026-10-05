"""Month, week, and day calendars of dated work."""

from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project
from keel.domain.enums import IssueStatus
from keel.services import issues as issue_service
from keel.services.home import _calendar_day, _completion_times
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
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_HOUR_LABELS = (
    "12 AM",
    "1 AM",
    "2 AM",
    "3 AM",
    "4 AM",
    "5 AM",
    "6 AM",
    "7 AM",
    "8 AM",
    "9 AM",
    "10 AM",
    "11 AM",
    "12 PM",
    "1 PM",
    "2 PM",
    "3 PM",
    "4 PM",
    "5 PM",
    "6 PM",
    "7 PM",
    "8 PM",
    "9 PM",
    "10 PM",
    "11 PM",
)
_DAY_MINUTES = 24 * 60
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
    status: IssueStatus
    column: int
    length: int
    lane: int
    continues_before: bool
    continues_after: bool


@dataclass(frozen=True)
class HourBlock:
    """One issue clipped to the hours of a single day."""

    key: str
    title: str
    project_key: str
    type: str
    status: IssueStatus
    start_minute: int
    end_minute: int
    lane: int
    lanes: int
    continues_before: bool
    continues_after: bool


@dataclass(frozen=True)
class CalendarDay:
    date: date
    in_month: bool
    is_today: bool
    mark: str = ""
    blocks: tuple[HourBlock, ...] = ()


@dataclass(frozen=True)
class CalendarWeek:
    days: tuple[CalendarDay, ...]
    spans: tuple[CalendarSpan, ...]


@dataclass(frozen=True)
class MonthCalendar:
    """The month page, the week page, or the day page."""

    label: str
    view: str
    month: str
    month_number: int
    day_number: int
    days_in_month: int
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
    day_href: str
    weeks: tuple[CalendarWeek, ...]
    empty: bool
    empty_note: str
    base: str
    hours: tuple[str, ...] = ()
    mode: str = "start"


@dataclass(frozen=True)
class _Bar:
    key: str
    title: str
    project_key: str
    type: str
    status: IssueStatus
    number: int
    start: date
    end: date
    start_at: datetime
    end_at: datetime


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


def chosen_day(
    raw: str | None,
    *,
    year: int | None,
    month_num: int | None,
    day_num: int | None,
    today: date,
) -> date:
    """The shown day. Dropdowns win, then `YYYY-MM-DD`, else today."""
    if year is not None and month_num is not None:
        first = parse_month(f"{year}-{month_num}", today)
        if day_num is None or day_num < 1:
            return first
        last = monthrange(first.year, first.month)[1]
        return date(first.year, first.month, min(day_num, last))
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


def parse_mode(raw: str | None) -> str:
    """`completed` and `created` select those dates. Anything else is start to due."""
    if raw in ("completed", "created"):
        return raw
    return "start"


def _link(base: str, query: str, mode: str) -> str:
    if mode == "start":
        return f"{base}?{query}" if query else base
    if query:
        return f"{base}?{query}&when={mode}"
    return f"{base}?when={mode}"


def _empty_note(mode: str, period: str) -> str:
    if mode == "start":
        if period == "day":
            return "Nothing dated falls on this day."
        return f"Nothing dated falls in this {period}."
    verb = "completed" if mode == "completed" else "created"
    if period == "day":
        return f"Nothing was {verb} on this day."
    return f"Nothing was {verb} in this {period}."


def open_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    view: str | None,
    month: str | None,
    week: str | None,
    day: str | None,
    year: int | None,
    month_num: int | None,
    day_num: int | None,
    today: date,
    project_id: int | None = None,
    base: str = "/calendar",
    filters: IssueFilters | None = None,
    mode: str = "start",
) -> MonthCalendar:
    """Month, week, or day for one person, one project, or a signed-out grid."""
    chosen = parse_mode(mode)
    if view == "week":
        focus = chosen_week(week, year=year, month_num=month_num, today=today)
        if project_id is None and assignee_id is None:
            return blank_week(focus, today=today, base=base, mode=chosen)
        return week_calendar(
            session,
            assignee_id,
            focus=focus,
            today=today,
            project_id=project_id,
            base=base,
            filters=filters,
            mode=chosen,
        )
    if view == "day":
        focus = chosen_day(
            day,
            year=year,
            month_num=month_num,
            day_num=day_num,
            today=today,
        )
        if project_id is None and assignee_id is None:
            return blank_day(focus, today=today, base=base, mode=chosen)
        return day_calendar(
            session,
            assignee_id,
            focus=focus,
            today=today,
            project_id=project_id,
            base=base,
            filters=filters,
            mode=chosen,
        )
    first = chosen_month(month, year=year, month_num=month_num, today=today)
    if project_id is None and assignee_id is None:
        return blank_month(first, today=today, base=base, mode=chosen)
    return month_calendar(
        session,
        assignee_id,
        month=first,
        today=today,
        project_id=project_id,
        base=base,
        filters=filters,
        mode=chosen,
    )


def month_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    month: date,
    today: date | None = None,
    project_id: int | None = None,
    base: str = "/calendar",
    filters: IssueFilters | None = None,
    mode: str = "start",
) -> MonthCalendar:
    """Issues for one person, or for one project, placed by the chosen dates."""
    day = today or date.today()
    chosen = parse_mode(mode)
    first = date(month.year, month.month, 1)
    grid_start, grid_end = _grid(first)
    bars = _bars(
        session,
        assignee_id,
        project_id,
        grid_start,
        grid_end,
        filters,
        chosen,
    )
    if bars is None:
        return blank_month(first, today=day, base=base, mode=chosen)
    return _describe_month(first, day, bars, base, chosen)


def week_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    focus: date,
    today: date | None = None,
    project_id: int | None = None,
    base: str = "/calendar",
    filters: IssueFilters | None = None,
    mode: str = "start",
) -> MonthCalendar:
    """Issues for one person, or for one project, placed by the chosen dates."""
    day = today or date.today()
    chosen = parse_mode(mode)
    monday = _monday(focus)
    bars = _bars(
        session,
        assignee_id,
        project_id,
        monday,
        monday + timedelta(days=6),
        filters,
        chosen,
    )
    if bars is None:
        return blank_week(focus, today=day, base=base, mode=chosen)
    return _describe_week(focus, day, bars, base, chosen)


def day_calendar(
    session: Session,
    assignee_id: int | None = None,
    *,
    focus: date,
    today: date | None = None,
    project_id: int | None = None,
    base: str = "/calendar",
    filters: IssueFilters | None = None,
    mode: str = "start",
) -> MonthCalendar:
    """Issues for one person, or for one project, placed by the chosen dates."""
    day = today or date.today()
    chosen = parse_mode(mode)
    bars = _bars(session, assignee_id, project_id, focus, focus, filters, chosen)
    if bars is None:
        return blank_day(focus, today=day, base=base, mode=chosen)
    return _describe_day(focus, day, bars, base, chosen)


def blank_month(
    month: date,
    *,
    today: date | None = None,
    base: str = "/calendar",
    mode: str = "start",
) -> MonthCalendar:
    """The same month grid with no issues, for a page that has no acting user."""
    day = today or date.today()
    return _describe_month(date(month.year, month.month, 1), day, (), base, mode)


def blank_week(
    focus: date,
    *,
    today: date | None = None,
    base: str = "/calendar",
    mode: str = "start",
) -> MonthCalendar:
    """The same week with no issues, for a page that has no acting user."""
    day = today or date.today()
    return _describe_week(focus, day, (), base, mode)


def blank_day(
    focus: date,
    *,
    today: date | None = None,
    base: str = "/calendar",
    mode: str = "start",
) -> MonthCalendar:
    """The same day with no issues, for a page that has no acting user."""
    day = today or date.today()
    return _describe_day(focus, day, (), base, mode)


def _bars(
    session: Session,
    assignee_id: int | None,
    project_id: int | None,
    start: date,
    end: date,
    filters: IssueFilters | None = None,
    mode: str = "start",
) -> list[_Bar] | None:
    statement = select(Issue, Project).join(Project, Issue.project_id == Project.id)
    if project_id is not None:
        statement = statement.where(Issue.project_id == project_id)
    elif assignee_id is not None:
        statement = statement.where(Issue.assignee_id == assignee_id)
    else:
        return None
    if filters is not None:
        statement = issue_service.restrict(statement, filters)
    found = list(session.execute(statement).all())
    completed = (
        _completion_times(session, [issue for issue, _project in found])
        if mode == "completed"
        else {}
    )
    bars: list[_Bar] = []
    for issue, project in found:
        placed = _placed(issue, mode, completed)
        if placed is None:
            continue
        bar_start, bar_end, start_at, end_at = placed
        if bar_end < start or bar_start > end:
            continue
        bars.append(
            _Bar(
                key=issue_service.issue_key(issue, project),
                title=issue.title,
                project_key=project.key,
                type=issue.type.value,
                status=issue.status,
                number=issue.number,
                start=bar_start,
                end=bar_end,
                start_at=start_at,
                end_at=end_at,
            ),
        )
    bars.sort(key=lambda bar: (bar.start, bar.project_key, bar.number))
    return bars


def _placed(
    issue: Issue,
    mode: str,
    completed: dict[int, datetime],
) -> tuple[date, date, datetime, datetime] | None:
    if mode == "completed":
        moment = completed.get(issue.id)
        if moment is None:
            return None
        return _point(moment)
    if mode == "created":
        return _point(issue.created_at)
    window = _window(issue)
    if window is None:
        return None
    start_at, end_at = _clock_span(issue)
    return window[0], window[1], start_at, end_at


def _point(moment: datetime) -> tuple[date, date, datetime, datetime]:
    """Local calendar day and clock of a UTC timestamp."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = moment.astimezone().replace(tzinfo=None)
    day = local.date()
    return day, day, local, local


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


def _clock(value: datetime) -> datetime:
    """The same clock Home uses for a calendar day, kept as a naive datetime."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _clock_span(issue: Issue) -> tuple[datetime, datetime]:
    start = _clock(issue.start_at) if issue.start_at is not None else None
    due = _clock(issue.due_at) if issue.due_at is not None else None
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
    mode: str = "start",
) -> MonthCalendar:
    weeks = _weeks(first, today, bars)
    anchor = _week_anchor(first, today)
    length = monthrange(first.year, first.month)[1]
    return MonthCalendar(
        label=f"{_MONTHS[first.month - 1]} {first.year}",
        view="month",
        month=_token(first),
        month_number=first.month,
        day_number=anchor.day,
        days_in_month=length,
        year=first.year,
        years=_year_choices(today, first),
        month_names=_MONTHS,
        prev_month=_token(_shift(first, -1)),
        next_month=_token(_shift(first, 1)),
        prev_href=_link(base, f"month={_token(_shift(first, -1))}", mode),
        next_href=_link(base, f"month={_token(_shift(first, 1))}", mode),
        today_href=_link(base, "", mode),
        month_href=_link(base, f"month={_token(first)}", mode),
        week_href=_link(base, f"view=week&week={anchor.isoformat()}", mode),
        day_href=_link(base, f"view=day&day={anchor.isoformat()}", mode),
        weeks=weeks,
        empty=not any(week.spans for week in weeks),
        empty_note=_empty_note(mode, "month"),
        base=base,
        mode=mode,
    )


def _describe_week(
    focus: date,
    today: date,
    bars: Sequence[_Bar],
    base: str,
    mode: str = "start",
) -> MonthCalendar:
    monday = _monday(focus)
    previous = _shift_week(monday, -1)
    following = _shift_week(monday, 1)
    days = _with_hours(_days(monday, today, month=None, mark_edges=True), bars)
    week = CalendarWeek(days=days, spans=())
    length = monthrange(focus.year, focus.month)[1]
    return MonthCalendar(
        label=_week_label(monday),
        view="week",
        month=_token(focus),
        month_number=focus.month,
        day_number=focus.day,
        days_in_month=length,
        year=focus.year,
        years=_year_choices(today, focus),
        month_names=_MONTHS,
        prev_month=previous.isoformat(),
        next_month=following.isoformat(),
        prev_href=_link(base, f"view=week&week={previous.isoformat()}", mode),
        next_href=_link(base, f"view=week&week={following.isoformat()}", mode),
        today_href=_link(base, "view=week", mode),
        month_href=_link(base, f"month={_token(focus)}", mode),
        week_href=_link(base, f"view=week&week={focus.isoformat()}", mode),
        day_href=_link(base, f"view=day&day={focus.isoformat()}", mode),
        weeks=(week,),
        empty=not any(day.blocks for day in days),
        empty_note=_empty_note(mode, "week"),
        base=base,
        hours=_HOUR_LABELS,
        mode=mode,
    )


def _describe_day(
    focus: date,
    today: date,
    bars: Sequence[_Bar],
    base: str,
    mode: str = "start",
) -> MonthCalendar:
    previous = _shift_day(focus, -1)
    following = _shift_day(focus, 1)
    shown_day = replace(
        CalendarDay(date=focus, in_month=True, is_today=focus == today),
        blocks=_blocks_on(bars, focus),
    )
    shown = CalendarWeek(days=(shown_day,), spans=())
    return MonthCalendar(
        label=_WEEKDAYS[focus.weekday()],
        view="day",
        month=_token(focus),
        month_number=focus.month,
        day_number=focus.day,
        days_in_month=monthrange(focus.year, focus.month)[1],
        year=focus.year,
        years=_year_choices(today, focus),
        month_names=_MONTHS,
        prev_month=previous.isoformat(),
        next_month=following.isoformat(),
        prev_href=_link(base, f"view=day&day={previous.isoformat()}", mode),
        next_href=_link(base, f"view=day&day={following.isoformat()}", mode),
        today_href=_link(base, "view=day", mode),
        month_href=_link(base, f"month={_token(focus)}", mode),
        week_href=_link(base, f"view=week&week={focus.isoformat()}", mode),
        day_href=_link(base, f"view=day&day={focus.isoformat()}", mode),
        weeks=(shown,),
        empty=not shown_day.blocks,
        empty_note=_empty_note(mode, "day"),
        base=base,
        hours=_HOUR_LABELS,
        mode=mode,
    )


def _with_hours(
    days: tuple[CalendarDay, ...],
    bars: Sequence[_Bar],
) -> tuple[CalendarDay, ...]:
    return tuple(replace(day, blocks=_blocks_on(bars, day.date)) for day in days)


def _blocks_on(bars: Sequence[_Bar], day: date) -> tuple[HourBlock, ...]:
    day_start = datetime(day.year, day.month, day.day)
    day_end = day_start + timedelta(days=1)
    pieces: list[tuple[_Bar, int, int, bool, bool]] = []
    for bar in bars:
        if bar.end_at < day_start or bar.start_at >= day_end:
            continue
        if bar.start_at == bar.end_at:
            if not day_start <= bar.start_at < day_end:
                continue
            start_minute = bar.start_at.hour * 60 + bar.start_at.minute
            pieces.append(
                (bar, start_minute, min(_DAY_MINUTES, start_minute + 60), False, False),
            )
            continue
        shown_start = max(bar.start_at, day_start)
        shown_end = min(bar.end_at, day_end)
        if shown_end <= shown_start:
            continue
        pieces.append(
            (
                bar,
                _minute(day_start, shown_start),
                _minute(day_start, shown_end, end=True),
                bar.start_at < day_start,
                bar.end_at > day_end,
            ),
        )
    pieces.sort(key=lambda piece: (piece[1], piece[0].project_key, piece[0].number))
    return _hour_lanes(pieces)


def _minute(origin: datetime, moment: datetime, *, end: bool = False) -> int:
    seconds = max(0, (moment - origin).total_seconds())
    if end:
        return min(_DAY_MINUTES, int((seconds + 59) // 60))
    return min(_DAY_MINUTES, int(seconds // 60))


def _hour_lanes(
    pieces: Sequence[tuple[_Bar, int, int, bool, bool]],
) -> tuple[HourBlock, ...]:
    until: list[int] = []
    placed: list[tuple[_Bar, int, int, bool, bool, int]] = []
    for bar, start_minute, end_minute, before, after in pieces:
        if end_minute <= start_minute:
            end_minute = min(_DAY_MINUTES, start_minute + 1)
        lane: int | None = None
        for index, occupied in enumerate(until):
            if start_minute >= occupied:
                until[index] = end_minute
                lane = index
                break
        if lane is None:
            until.append(end_minute)
            lane = len(until) - 1
        placed.append((bar, start_minute, end_minute, before, after, lane))
    count = max(len(until), 1)
    return tuple(
        HourBlock(
            key=bar.key,
            title=bar.title,
            project_key=bar.project_key,
            type=bar.type,
            status=bar.status,
            start_minute=start_minute,
            end_minute=end_minute,
            lane=lane,
            lanes=count,
            continues_before=before,
            continues_after=after,
        )
        for bar, start_minute, end_minute, before, after, lane in placed
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
                status=bar.status,
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


def _shift_day(shown: date, delta: int) -> date:
    try:
        shifted = shown + timedelta(days=delta)
    except OverflowError:
        return shown
    if shifted < date(1, 1, 1):
        return date(1, 1, 1)
    return shifted


def _token(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"
