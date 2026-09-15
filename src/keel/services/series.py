"""Repeating series: recipes, Outlook-scoped edits, and spawn catch-up."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Series, SeriesSkip, Sprint
from keel.domain.enums import (
    CLOSED_STATUSES,
    EditScope,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
    SprintState,
)
from keel.domain.errors import InvalidSeriesError, NotFoundError, SeriesStoppedError
from keel.domain.recurrence import (
    Recurrence,
    encode_weekdays,
    next_on_or_after,
    occurrence_dates,
    parse_weekdays,
)
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service

MAX_TITLE_LENGTH = 300
UNSET = object()
HORIZON_DAYS = 366 * 2


def get_series(session: Session, series_id: int) -> Series:
    series = _require_series(session, series_id)
    if series.state is SeriesState.STOPPED:
        _retire_series(session, series)
        raise NotFoundError(f"No series with id {series_id}.")
    return series


def list_series(session: Session, project_id: int) -> Sequence[Series]:
    project_service.get_project(session, project_id)
    _retire_stopped(session, project_id)
    return session.scalars(
        select(Series)
        .where(
            Series.project_id == project_id,
            Series.state != SeriesState.STOPPED,
        )
        .order_by(Series.title, Series.id),
    ).all()


def attached_series(session: Session, issue: Issue) -> Series | None:
    """Live recipe for an issue, retiring leftover Stopped series first."""
    if issue.series_id is None:
        return None
    series = session.get(Series, issue.series_id)
    if series is None:
        return None
    if series.state is SeriesState.STOPPED:
        _retire_series(session, series)
        session.refresh(issue)
        return None
    return series


def delete_series(session: Session, series_id: int) -> None:
    _retire_series(session, _require_series(session, series_id))


def cadence_summary(series: Series) -> str:
    return recurrence_of(series).summary()


def create_series(
    session: Session,
    project_id: int,
    *,
    title: str,
    type: IssueType,
    spawn_mode: SeriesSpawnMode,
    sprint_basis: SeriesSprintBasis,
    freq: RecurrenceFreq,
    starts_on: date,
    description: str = "",
    interval: int = 1,
    weekdays: tuple[int, ...] = (),
    month_day: int | None = None,
    nth_week: int | None = None,
    month: int | None = None,
    ends_on: date | None = None,
    occurrence_count: int | None = None,
    look_ahead_n: int = 1,
    parent_id: int | None = None,
    assignee_id: int | None = None,
    reporter_id: int | None = None,
    seed_issue_id: int | None = None,
    today: date | None = None,
) -> Series:
    project = project_service.get_project(session, project_id)
    today = today or date.today()
    recurrence = Recurrence(
        freq=freq,
        starts_on=starts_on,
        interval=interval,
        weekdays=weekdays,
        month_day=month_day,
        nth_week=nth_week,
        month=month,
        ends_on=ends_on,
        count=occurrence_count,
    )
    occurrence_dates(recurrence, starts_on)
    series = Series(
        project_id=project.id,
        title=_clean_title(title),
        description=description.strip(),
        type=type,
        spawn_mode=spawn_mode,
        sprint_basis=sprint_basis,
        look_ahead_n=_look_ahead(look_ahead_n),
        freq=freq,
        interval=interval,
        weekdays=encode_weekdays(weekdays),
        month_day=month_day,
        nth_week=nth_week,
        month=month,
        starts_on=starts_on,
        ends_on=ends_on,
        occurrence_count=occurrence_count,
        parent_id=parent_id,
        assignee_id=assignee_id,
        reporter_id=reporter_id,
    )
    session.add(series)
    session.flush()
    if seed_issue_id is not None:
        _attach_seed(session, series, seed_issue_id, today)
    advance_series(session, series.id, today)
    return series


def update_series(
    session: Session,
    series_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    type: IssueType | None = None,
    spawn_mode: SeriesSpawnMode | None = None,
    sprint_basis: SeriesSprintBasis | None = None,
    look_ahead_n: int | None = None,
    freq: RecurrenceFreq | None = None,
    interval: int | None = None,
    weekdays: tuple[int, ...] | None = None,
    month_day: int | None | object = UNSET,
    nth_week: int | None | object = UNSET,
    month: int | None | object = UNSET,
    starts_on: date | None = None,
    ends_on: date | None | object = UNSET,
    occurrence_count: int | None | object = UNSET,
    parent_id: int | None | object = UNSET,
    assignee_id: int | None | object = UNSET,
    today: date | None = None,
) -> Series:
    series = get_series(session, series_id)
    if title is not None:
        series.title = _clean_title(title)
    if description is not None:
        series.description = description.strip()
    if type is not None:
        series.type = type
    if spawn_mode is not None:
        series.spawn_mode = spawn_mode
    if sprint_basis is not None:
        series.sprint_basis = sprint_basis
    if look_ahead_n is not None:
        series.look_ahead_n = _look_ahead(look_ahead_n)
    if freq is not None:
        series.freq = freq
    if interval is not None:
        series.interval = interval
    if weekdays is not None:
        series.weekdays = encode_weekdays(weekdays)
    if month_day is not UNSET:
        series.month_day = month_day  # type: ignore[assignment]
    if nth_week is not UNSET:
        series.nth_week = nth_week  # type: ignore[assignment]
    if month is not UNSET:
        series.month = month  # type: ignore[assignment]
    if starts_on is not None:
        series.starts_on = starts_on
    if ends_on is not UNSET:
        series.ends_on = ends_on  # type: ignore[assignment]
    if occurrence_count is not UNSET:
        series.occurrence_count = occurrence_count  # type: ignore[assignment]
    if parent_id is not UNSET:
        series.parent_id = parent_id  # type: ignore[assignment]
    if assignee_id is not UNSET:
        series.assignee_id = assignee_id  # type: ignore[assignment]
    occurrence_dates(recurrence_of(series), series.starts_on)
    session.flush()
    advance_series(session, series.id, today or date.today())
    return series


def set_state(
    session: Session,
    series_id: int,
    state: SeriesState,
    today: date | None = None,
) -> Series:
    if state is SeriesState.STOPPED:
        raise SeriesStoppedError("A series is ended by deleting it.")
    series = get_series(session, series_id)
    series.state = state
    session.flush()
    if state is SeriesState.ACTIVE:
        advance_series(session, series.id, today or date.today())
    return series


def apply_occurrence_edit(
    session: Session,
    issue_id: int,
    scope: EditScope,
    *,
    title: str | None = None,
    description: str | None = None,
    type: IssueType | None = None,
    assignee_id: int | None | object = UNSET,
    parent_id: int | None | object = UNSET,
    spawn_mode: SeriesSpawnMode | None = None,
    sprint_basis: SeriesSprintBasis | None = None,
    look_ahead_n: int | None = None,
    freq: RecurrenceFreq | None = None,
    interval: int | None = None,
    weekdays: tuple[int, ...] | None = None,
    month_day: int | None | object = UNSET,
    nth_week: int | None | object = UNSET,
    month: int | None | object = UNSET,
    starts_on: date | None = None,
    ends_on: date | None | object = UNSET,
    occurrence_count: int | None | object = UNSET,
    today: date | None = None,
) -> Issue:
    issue = issue_service.get_issue(session, issue_id)
    if issue.series_id is None:
        raise InvalidSeriesError("This issue is not part of a series.")
    series = get_series(session, issue.series_id)
    if scope is EditScope.THIS:
        _update_one_issue(
            session,
            issue,
            title=title,
            description=description,
            type=type,
            assignee_id=assignee_id,
            parent_id=parent_id,
        )
        return issue
    cutoff = issue.occurrence_on
    update_series(
        session,
        series.id,
        title=title,
        description=description,
        type=type,
        spawn_mode=spawn_mode,
        sprint_basis=sprint_basis,
        look_ahead_n=look_ahead_n,
        freq=freq,
        interval=interval,
        weekdays=weekdays,
        month_day=month_day,
        nth_week=nth_week,
        month=month,
        starts_on=starts_on,
        ends_on=ends_on,
        occurrence_count=occurrence_count,
        parent_id=parent_id,
        assignee_id=assignee_id,
        today=today,
    )
    for copy in _copies(session, series.id):
        if scope is EditScope.FUTURE and (
            cutoff is None or copy.occurrence_on is None or copy.occurrence_on < cutoff
        ):
            continue
        if copy.status in CLOSED_STATUSES:
            continue
        _update_one_issue(
            session,
            copy,
            title=title,
            description=description,
            type=type,
            assignee_id=assignee_id,
            parent_id=parent_id,
        )
    return issue


def after_issue_deleted(
    session: Session,
    series_id: int,
    occurrence_on: date,
    today: date | None = None,
) -> None:
    _record_skip(session, series_id, occurrence_on)
    advance_series(session, series_id, today or date.today())


def on_occurrence_closed(
    session: Session,
    issue: Issue,
    today: date | None = None,
) -> None:
    if issue.series_id is None:
        return
    if issue.status not in CLOSED_STATUSES:
        return
    advance_series(session, issue.series_id, today or date.today())


def advance_all(session: Session, today: date | None = None) -> None:
    today = today or date.today()
    _retire_stopped(session)
    rows = session.scalars(
        select(Series).where(Series.state == SeriesState.ACTIVE),
    ).all()
    for series in rows:
        advance_series(session, series.id, today)


def advance_series(session: Session, series_id: int, today: date | None = None) -> None:
    series = get_series(session, series_id)
    if series.state is not SeriesState.ACTIVE:
        return
    today = today or date.today()
    windows = _open_windows(session, series.project_id)
    _claim_previews(session, series, windows)
    existing = _existing_dates(session, series.id)
    skips = _skipped_dates(session, series.id)
    if series.spawn_mode is SeriesSpawnMode.AFTER_CLOSED:
        _spawn_after_closed(session, series, today, existing, skips, windows)
        return
    _spawn_calendar(session, series, today, existing, skips, windows)


def recurrence_of(series: Series) -> Recurrence:
    return Recurrence(
        freq=series.freq,
        starts_on=series.starts_on,
        interval=series.interval,
        weekdays=parse_weekdays(series.weekdays),
        month_day=series.month_day,
        nth_week=series.nth_week,
        month=series.month,
        ends_on=series.ends_on,
        count=series.occurrence_count,
    )


def _spawn_after_closed(
    session: Session,
    series: Series,
    today: date,
    existing: set[date],
    skips: set[date],
    windows: Sequence[Sprint],
) -> None:
    open_copies = [
        issue
        for issue in _copies(session, series.id)
        if issue.status not in CLOSED_STATUSES
    ]
    if open_copies:
        return
    nxt = next_on_or_after(
        recurrence_of(series),
        today,
        skip=skips,
        existing=existing,
    )
    if nxt is None:
        return
    _spawn_one(session, series, nxt, windows)


def _spawn_calendar(
    session: Session,
    series: Series,
    today: date,
    existing: set[date],
    skips: set[date],
    windows: Sequence[Sprint],
) -> None:
    horizon = today + timedelta(days=HORIZON_DAYS)
    dates = [
        occ
        for occ in occurrence_dates(recurrence_of(series), horizon)
        if occ not in existing and occ not in skips
    ]
    if series.sprint_basis is SeriesSprintBasis.CREATED_ON:
        dates = [occ for occ in dates if occ <= today]
    with_window: list[date] = []
    without: list[date] = []
    for occ in dates:
        if _overlapping(windows, occ) is None:
            without.append(occ)
        else:
            with_window.append(occ)
    open_unscheduled = sum(
        1
        for issue in _copies(session, series.id)
        if issue.sprint_id is None and issue.status not in CLOSED_STATUSES
    )
    slots = max(0, series.look_ahead_n - open_unscheduled)
    chosen = with_window + without[:slots]
    for occ in chosen:
        _spawn_one(session, series, occ, windows)


def _spawn_one(
    session: Session,
    series: Series,
    occurrence_on: date,
    windows: Sequence[Sprint],
) -> Issue:
    sprint = _overlapping(windows, occurrence_on)
    issue = issue_service.create_issue(
        session,
        series.project_id,
        type=series.type,
        title=series.title,
        description=series.description,
        parent_id=series.parent_id,
        reporter_id=series.reporter_id,
        assignee_id=series.assignee_id,
        due_at=datetime(occurrence_on.year, occurrence_on.month, occurrence_on.day),
        sprint_id=None if sprint is None else sprint.id,
        series_id=series.id,
        occurrence_on=occurrence_on,
    )
    return issue


def _claim_previews(
    session: Session,
    series: Series,
    windows: Sequence[Sprint],
) -> None:
    for issue in _copies(session, series.id):
        if issue.sprint_id is not None or issue.occurrence_on is None:
            continue
        if issue.status in CLOSED_STATUSES:
            continue
        sprint = _overlapping(windows, issue.occurrence_on)
        if sprint is not None:
            issue.sprint_id = sprint.id
    session.flush()


def _overlapping(windows: Sequence[Sprint], day: date) -> Sprint | None:
    matches = [
        sprint
        for sprint in windows
        if sprint.starts_on is not None
        and sprint.ends_on is not None
        and sprint.starts_on <= day <= sprint.ends_on
    ]
    if not matches:
        return None
    matches.sort(key=lambda sprint: (sprint.starts_on or day, sprint.id))
    return matches[0]


def _open_windows(session: Session, project_id: int) -> Sequence[Sprint]:
    return [
        sprint
        for sprint in sprint_service.list_sprints(session, project_id)
        if sprint.state is not SprintState.COMPLETED
    ]


def _copies(session: Session, series_id: int) -> Sequence[Issue]:
    return session.scalars(
        select(Issue)
        .where(Issue.series_id == series_id)
        .order_by(Issue.occurrence_on, Issue.id),
    ).all()


def _existing_dates(session: Session, series_id: int) -> set[date]:
    return {
        issue.occurrence_on
        for issue in _copies(session, series_id)
        if issue.occurrence_on is not None
    }


def _skipped_dates(session: Session, series_id: int) -> set[date]:
    return set(
        session.scalars(
            select(SeriesSkip.occurrence_on).where(SeriesSkip.series_id == series_id),
        ).all(),
    )


def _record_skip(session: Session, series_id: int, occurrence_on: date) -> None:
    if occurrence_on in _skipped_dates(session, series_id):
        return
    session.add(SeriesSkip(series_id=series_id, occurrence_on=occurrence_on))
    session.flush()


def _attach_seed(
    session: Session,
    series: Series,
    issue_id: int,
    today: date,
) -> None:
    issue = issue_service.get_issue(session, issue_id)
    if issue.project_id != series.project_id:
        raise InvalidSeriesError(
            "A series can only start from an issue in its project."
        )
    if issue.series_id is not None:
        raise InvalidSeriesError("That issue already belongs to a series.")
    occurrence = issue.due_at.date() if issue.due_at is not None else today
    issue.series_id = series.id
    issue.occurrence_on = occurrence
    issue.former_series_title = None
    issue.former_series_cadence = None
    session.flush()


def _update_one_issue(
    session: Session,
    issue: Issue,
    *,
    title: str | None,
    description: str | None,
    type: IssueType | None,
    assignee_id: int | None | object,
    parent_id: int | None | object,
) -> None:
    kwargs: dict[str, object] = {}
    if title is not None:
        kwargs["title"] = title
    if description is not None:
        kwargs["description"] = description
    if type is not None:
        kwargs["type"] = type
    if assignee_id is not UNSET:
        kwargs["assignee_id"] = assignee_id
    if parent_id is not UNSET:
        kwargs["parent_id"] = parent_id
    if kwargs:
        issue_service.update_issue(session, issue.id, **kwargs)  # type: ignore[arg-type]


def _require_series(session: Session, series_id: int) -> Series:
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"No series with id {series_id}.")
    return series


def _retire_stopped(session: Session, project_id: int | None = None) -> None:
    query = select(Series).where(Series.state == SeriesState.STOPPED)
    if project_id is not None:
        query = query.where(Series.project_id == project_id)
    for series in session.scalars(query).all():
        _retire_series(session, series)


def _retire_series(session: Session, series: Series) -> None:
    summary = cadence_summary(series)
    for issue in _copies(session, series.id):
        issue.former_series_title = series.title
        issue.former_series_cadence = summary
        issue.series_id = None
    session.delete(series)
    session.flush()


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise InvalidSeriesError("A series needs a title.")
    return cleaned[:MAX_TITLE_LENGTH]


def _look_ahead(value: int) -> int:
    if value < 1:
        raise InvalidSeriesError("Look-ahead must be at least 1.")
    return value
