"""Repeating series: recipes, Outlook-scoped edits, and spawn catch-up."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Series, SeriesItem, SeriesSkip, Sprint
from keel.domain.enums import (
    CLOSED_STATUSES,
    INITIAL_PRIORITY,
    EditScope,
    IssuePriority,
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
from keel.domain.schedule import (
    check_recipe_window,
    complete_offset_pair,
    offsets_for_window,
    recipe_due_at,
    recipe_start_at,
)
from keel.services import history as history_service
from keel.services import issues as issue_service
from keel.services import labels as label_service
from keel.services import projects as project_service
from keel.services import series_tree
from keel.services import sprints as sprint_service
from keel.services.series_tree import ItemDraft

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
    priority: IssuePriority = INITIAL_PRIORITY,
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
    start_offset_days: int | None = 0,
    start_minute_of_day: int | None = 0,
    due_offset_days: int | None = 0,
    due_minute_of_day: int | None = 0,
    labels: Sequence[str] | None = None,
    items: Sequence[ItemDraft] | None = None,
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
    start_offset_days, start_minute_of_day = complete_offset_pair(
        start_offset_days,
        start_minute_of_day,
    )
    due_offset_days, due_minute_of_day = complete_offset_pair(
        due_offset_days,
        due_minute_of_day,
    )
    series = Series(
        project_id=project.id,
        title=_clean_title(title),
        description=description.strip(),
        type=type,
        priority=priority,
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
        start_offset_days=start_offset_days,
        start_minute_of_day=start_minute_of_day,
        due_offset_days=due_offset_days,
        due_minute_of_day=due_minute_of_day,
    )
    session.add(series)
    session.flush()
    if labels is not None:
        label_service.set_series_labels(session, series.id, labels)
    elif seed_issue_id is not None:
        label_service.set_series_labels(
            session,
            series.id,
            label_service.names_for_issue(session, seed_issue_id),
        )
    if seed_issue_id is not None:
        _attach_seed(session, series, seed_issue_id, today)
    if items:
        series_tree.replace_items(session, series, items)
        if seed_issue_id is not None:
            seed = issue_service.get_issue(session, seed_issue_id)
            if seed.occurrence_on is not None:
                _spawn_children(
                    session,
                    series,
                    seed.occurrence_on,
                    seed,
                    _open_windows(session, series.project_id),
                )
    elif seed_issue_id is not None:
        seed = issue_service.get_issue(session, seed_issue_id)
        if seed.occurrence_on is not None:
            series_tree.seed_descendants(session, series, seed, seed.occurrence_on)
    _check_offsets(series)
    advance_series(session, series.id, today)
    return series


def update_series(
    session: Session,
    series_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    type: IssueType | None = None,
    priority: IssuePriority | None = None,
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
    start_offset_days: int | None | object = UNSET,
    start_minute_of_day: int | None | object = UNSET,
    due_offset_days: int | None | object = UNSET,
    due_minute_of_day: int | None | object = UNSET,
    labels: Sequence[str] | None = None,
    items: Sequence[ItemDraft] | object = UNSET,
    rewrite_from: date | None = None,
    today: date | None = None,
) -> Series:
    series = get_series(session, series_id)
    if title is not None:
        series.title = _clean_title(title)
    if description is not None:
        series.description = description.strip()
    if type is not None:
        series.type = type
    if priority is not None:
        series.priority = priority
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
    _assign_start(series, start_offset_days, start_minute_of_day)
    _assign_due(series, due_offset_days, due_minute_of_day)
    if labels is not None:
        label_service.set_series_labels(session, series.id, labels)
    if items is not UNSET:
        series_tree.replace_items(session, series, items)  # type: ignore[arg-type]
    _check_offsets(series)
    occurrence_dates(recurrence_of(series), series.starts_on)
    session.flush()
    _sync_copy_dates(session, series, from_on=rewrite_from)
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
    priority: IssuePriority | None = None,
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
    start_offset_days: int | None | object = UNSET,
    start_minute_of_day: int | None | object = UNSET,
    due_offset_days: int | None | object = UNSET,
    due_minute_of_day: int | None | object = UNSET,
    start_at: datetime | None | object = UNSET,
    due_at: datetime | None | object = UNSET,
    labels: Sequence[str] | None = None,
    item_action: str | None = None,
    item: ItemDraft | None = None,
    today: date | None = None,
    actor_name: str | None = None,
) -> Issue:
    issue = issue_service.get_issue(session, issue_id)
    if issue.series_id is None:
        raise InvalidSeriesError("This issue is not part of a series.")
    series = get_series(session, issue.series_id)
    if item_action == "add":
        if item is None:
            raise InvalidSeriesError("An added item needs a title.")
        _add_tree_item(
            session,
            issue,
            series,
            scope,
            item,
            actor_name=actor_name,
        )
        return issue
    if item_action == "remove":
        _remove_tree_item(session, issue, series, scope)
        return issue
    if scope is EditScope.THIS:
        _update_one_issue(
            session,
            issue,
            title=title,
            description=description,
            type=type,
            priority=priority,
            assignee_id=assignee_id,
            parent_id=parent_id,
            start_at=start_at,
            due_at=due_at,
            labels=labels,
            actor_name=actor_name,
        )
        return issue
    if issue.series_item_id is not None:
        return _apply_item_edit(
            session,
            issue,
            series,
            scope,
            title=title,
            description=description,
            type=type,
            priority=priority,
            assignee_id=assignee_id,
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
            start_offset_days=start_offset_days,
            start_minute_of_day=start_minute_of_day,
            due_offset_days=due_offset_days,
            due_minute_of_day=due_minute_of_day,
            start_at=start_at,
            due_at=due_at,
            labels=labels,
            today=today,
            actor_name=actor_name,
        )
    if start_at is not UNSET or due_at is not UNSET:
        start_offset_days, start_minute_of_day, due_offset_days, due_minute_of_day = (
            _offsets_from_datetimes(issue, start_at, due_at)
        )
    cutoff = issue.occurrence_on
    update_series(
        session,
        series.id,
        title=title,
        description=description,
        type=type,
        priority=priority,
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
        start_offset_days=start_offset_days,
        start_minute_of_day=start_minute_of_day,
        due_offset_days=due_offset_days,
        due_minute_of_day=due_minute_of_day,
        labels=labels,
        rewrite_from=cutoff if scope is EditScope.FUTURE else None,
        today=today,
    )
    for copy in _copies(session, series.id):
        if copy.series_item_id != issue.series_item_id:
            continue
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
            priority=priority,
            assignee_id=assignee_id,
            parent_id=parent_id,
            labels=labels,
            actor_name=actor_name,
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
        if issue.series_item_id is None and issue.status not in CLOSED_STATUSES
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
        if _overlapping(windows, _placement_day(series, occ)) is None:
            without.append(occ)
        else:
            with_window.append(occ)
    open_unscheduled = sum(
        1
        for issue in _copies(session, series.id)
        if issue.series_item_id is None
        and issue.sprint_id is None
        and issue.status not in CLOSED_STATUSES
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
    start_at, due_at = occurrence_window(series, occurrence_on)
    sprint = _overlapping(windows, _placement_day(series, occurrence_on))
    issue = issue_service.create_issue(
        session,
        series.project_id,
        type=series.type,
        title=series.title,
        description=series.description,
        priority=series.priority,
        parent_id=series.parent_id,
        reporter_id=series.reporter_id,
        assignee_id=series.assignee_id,
        start_at=start_at,
        due_at=due_at,
        sprint_id=None if sprint is None else sprint.id,
        series_id=series.id,
        occurrence_on=occurrence_on,
    )
    names = label_service.names_for_series(session, series.id)
    if names:
        label_service.set_issue_labels(
            session,
            issue.id,
            names,
            actor_name=history_service.SYSTEM_ACTOR,
        )
    _spawn_children(session, series, occurrence_on, issue, windows)
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
        day = _claim_day(session, series, issue)
        if day is None:
            continue
        sprint = _overlapping(windows, day)
        if sprint is not None:
            from keel.services import history as history_service

            history_service.record(
                session,
                issue.id,
                field=history_service.FIELD_SPRINT,
                from_value=history_service.sprint_label(session, issue.sprint_id),
                to_value=sprint.name,
                actor_name=history_service.SYSTEM_ACTOR,
            )
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
        if issue.series_item_id is None and issue.occurrence_on is not None
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
    occurrence = (
        issue.due_at.date()
        if issue.due_at is not None
        else issue.start_at.date()
        if issue.start_at is not None
        else today
    )
    if issue.start_at is not None or issue.due_at is not None:
        (
            series.start_offset_days,
            series.start_minute_of_day,
            series.due_offset_days,
            series.due_minute_of_day,
        ) = _offsets_from_issue(issue, occurrence)
    issue.series_id = series.id
    issue.occurrence_on = occurrence
    start_at, due_at = occurrence_window(series, occurrence)
    if issue.start_at is None:
        issue.start_at = start_at
    if issue.due_at is None:
        issue.due_at = due_at
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
    priority: IssuePriority | None,
    assignee_id: int | None | object,
    parent_id: int | None | object,
    start_at: datetime | None | object = UNSET,
    due_at: datetime | None | object = UNSET,
    labels: Sequence[str] | None = None,
    actor_name: str | None = None,
) -> None:
    kwargs: dict[str, object] = {}
    if title is not None:
        kwargs["title"] = title
    if description is not None:
        kwargs["description"] = description
    if type is not None:
        kwargs["type"] = type
    if priority is not None:
        kwargs["priority"] = priority
    if assignee_id is not UNSET:
        kwargs["assignee_id"] = assignee_id
    if parent_id is not UNSET:
        kwargs["parent_id"] = parent_id
    if start_at is not UNSET:
        kwargs["start_at"] = start_at
    if due_at is not UNSET:
        kwargs["due_at"] = due_at
    if labels is not None:
        label_service.set_issue_labels(
            session,
            issue.id,
            labels,
            actor_name=actor_name,
        )
    if kwargs:
        issue_service.update_issue(
            session,
            issue.id,
            actor_name=actor_name,
            **kwargs,  # type: ignore[arg-type]
        )


def occurrence_window(
    series: Series,
    occurrence_on: date,
) -> tuple[datetime | None, datetime | None]:
    return (
        recipe_start_at(
            occurrence_on,
            series.start_offset_days,
            series.start_minute_of_day,
        ),
        recipe_due_at(
            occurrence_on,
            series.due_offset_days,
            series.due_minute_of_day,
        ),
    )


def _check_offsets(series: Series) -> None:
    check_recipe_window(
        series.start_offset_days,
        series.start_minute_of_day,
        series.due_offset_days,
        series.due_minute_of_day,
    )


def _sync_copy_dates(
    session: Session,
    series: Series,
    *,
    from_on: date | None,
) -> None:
    for copy in _copies(session, series.id):
        if copy.series_item_id is not None or copy.occurrence_on is None:
            continue
        if from_on is not None and copy.occurrence_on < from_on:
            continue
        if copy.status in CLOSED_STATUSES:
            continue
        start_at, due_at = occurrence_window(series, copy.occurrence_on)
        issue_service.update_issue(
            session,
            copy.id,
            start_at=start_at,
            due_at=due_at,
        )


def _placement_day(series: Series, occurrence_on: date) -> date:
    start_at, due_at = occurrence_window(series, occurrence_on)
    if series.sprint_basis is SeriesSprintBasis.START_ON:
        if start_at is not None:
            return start_at.date()
        return occurrence_on
    if series.sprint_basis is SeriesSprintBasis.CREATED_ON:
        return occurrence_on
    if due_at is not None:
        return due_at.date()
    return occurrence_on


def _claim_day(session: Session, series: Series, issue: Issue) -> date | None:
    if issue.occurrence_on is None:
        return date.today()
    if issue.series_item_id is not None:
        item = session.get(SeriesItem, issue.series_item_id)
        if item is None or item.removed:
            return None
        return _item_placement(series, item, issue.occurrence_on)
    if series.sprint_basis is SeriesSprintBasis.START_ON:
        if issue.start_at is not None:
            return issue.start_at.date()
        start_at, _due_at = occurrence_window(series, issue.occurrence_on)
        if start_at is not None:
            return start_at.date()
        return issue.occurrence_on
    if series.sprint_basis is SeriesSprintBasis.CREATED_ON:
        return issue.occurrence_on
    if issue.due_at is not None:
        return issue.due_at.date()
    _start_at, due_at = occurrence_window(series, issue.occurrence_on)
    if due_at is not None:
        return due_at.date()
    return issue.occurrence_on


def _offsets_from_issue(
    issue: Issue,
    occurrence_on: date,
) -> tuple[int | None, int | None, int | None, int | None]:
    return offsets_for_window(occurrence_on, issue.start_at, issue.due_at)


def _offsets_from_datetimes(
    issue: Issue,
    start_at: datetime | None | object,
    due_at: datetime | None | object,
) -> tuple[int | None, int | None, int | None, int | None]:
    if issue.occurrence_on is None:
        raise InvalidSeriesError("This copy has no occurrence date.")
    return offsets_for_window(
        issue.occurrence_on,
        _optional_instant(start_at, issue.start_at),
        _optional_instant(due_at, issue.due_at),
    )


def _optional_instant(
    value: datetime | None | object,
    current: datetime | None,
) -> datetime | None:
    if value is UNSET:
        return current
    if value is None or isinstance(value, datetime):
        return value
    raise InvalidSeriesError("A date could not be read.")


def _merged_offset(value: int | None | object, current: int | None) -> int | None:
    if value is UNSET:
        return current
    if value is None or isinstance(value, int):
        return value
    raise InvalidSeriesError("Day offset could not be read.")


def _assign_start(
    series: Series,
    offset_days: int | None | object,
    minute_of_day: int | None | object,
) -> None:
    if offset_days is UNSET and minute_of_day is UNSET:
        return
    series.start_offset_days, series.start_minute_of_day = complete_offset_pair(
        _merged_offset(offset_days, series.start_offset_days),
        _merged_offset(minute_of_day, series.start_minute_of_day),
    )


def _assign_due(
    series: Series,
    offset_days: int | None | object,
    minute_of_day: int | None | object,
) -> None:
    if offset_days is UNSET and minute_of_day is UNSET:
        return
    series.due_offset_days, series.due_minute_of_day = complete_offset_pair(
        _merged_offset(offset_days, series.due_offset_days),
        _merged_offset(minute_of_day, series.due_minute_of_day),
    )


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
        issue.series_item_id = None
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


def delete_occurrence(session: Session, issue: Issue) -> None:
    """Remove one occurrence's whole tree and skip that date."""
    if issue.series_id is None or issue.occurrence_on is None:
        raise InvalidSeriesError("This issue is not part of a series.")
    members = [
        copy
        for copy in _copies(session, issue.series_id)
        if copy.occurrence_on == issue.occurrence_on and copy.id != issue.id
    ]
    _delete_members(session, members)
    children = issue_service.list_children(session, issue.id)
    if children:
        from keel.domain.errors import IssueHasChildrenError

        raise IssueHasChildrenError(
            "Move or delete this issue's children first.",
            issue_id=issue.id,
            children=len(children),
        )
    series_id = issue.series_id
    occurrence_on = issue.occurrence_on
    session.delete(issue)
    session.flush()
    after_issue_deleted(session, series_id, occurrence_on)


def _spawn_children(
    session: Session,
    series: Series,
    occurrence_on: date,
    root: Issue,
    windows: Sequence[Sprint],
) -> None:
    spawned: dict[int, Issue] = {}
    for item in series_tree.active_items(session, series.id):
        parent: Issue
        if item.parent_item_id is None:
            parent = root
        else:
            found = spawned.get(item.parent_item_id)
            if found is None:
                raise InvalidSeriesError("The schedule tree could not be read.")
            parent = found
        spawned[item.id] = _spawn_item(
            session,
            series,
            item,
            occurrence_on,
            parent,
            windows,
        )


def _spawn_item(
    session: Session,
    series: Series,
    item: SeriesItem,
    occurrence_on: date,
    parent: Issue,
    windows: Sequence[Sprint],
) -> Issue:
    start_at, due_at = _item_window(item, occurrence_on)
    day = _item_placement(series, item, occurrence_on)
    sprint = None if day is None else _overlapping(windows, day)
    issue = issue_service.create_issue(
        session,
        series.project_id,
        type=item.type,
        title=item.title,
        description=item.description,
        priority=item.priority,
        parent_id=parent.id,
        reporter_id=series.reporter_id,
        assignee_id=item.assignee_id,
        start_at=start_at,
        due_at=due_at,
        sprint_id=None if sprint is None else sprint.id,
        series_id=series.id,
        series_item_id=item.id,
        occurrence_on=occurrence_on,
    )
    names = label_service.names_for_series_item(session, item.id)
    if names:
        label_service.set_issue_labels(
            session,
            issue.id,
            names,
            actor_name=history_service.SYSTEM_ACTOR,
        )
    return issue


def _item_window(
    item: SeriesItem,
    occurrence_on: date,
) -> tuple[datetime | None, datetime | None]:
    return (
        recipe_start_at(
            occurrence_on,
            item.start_offset_days,
            item.start_minute_of_day,
        ),
        recipe_due_at(
            occurrence_on,
            item.due_offset_days,
            item.due_minute_of_day,
        ),
    )


def _item_placement(
    series: Series,
    item: SeriesItem,
    occurrence_on: date,
) -> date | None:
    start_at, due_at = _item_window(item, occurrence_on)
    if series.sprint_basis is SeriesSprintBasis.CREATED_ON:
        return occurrence_on
    if series.sprint_basis is SeriesSprintBasis.START_ON:
        return None if start_at is None else start_at.date()
    return None if due_at is None else due_at.date()


def _add_tree_item(
    session: Session,
    issue: Issue,
    series: Series,
    scope: EditScope,
    draft: ItemDraft,
    *,
    actor_name: str | None,
) -> None:
    if scope is EditScope.THIS:
        series_tree.require_child(draft.type, issue.type)
    else:
        parent_type = series.type
        if issue.series_item_id is not None:
            parent = session.get(SeriesItem, issue.series_item_id)
            if parent is not None:
                parent_type = parent.type
        series_tree.require_child(draft.type, parent_type)
    if scope is EditScope.THIS:
        occurrence = issue.occurrence_on or date.today()
        start_days, start_minute = complete_offset_pair(
            draft.start_offset_days,
            draft.start_minute_of_day,
        )
        due_days, due_minute = complete_offset_pair(
            draft.due_offset_days,
            draft.due_minute_of_day,
        )
        check_recipe_window(start_days, start_minute, due_days, due_minute)
        start_at = recipe_start_at(occurrence, start_days, start_minute)
        due_at = recipe_due_at(occurrence, due_days, due_minute)
        created = issue_service.create_issue(
            session,
            series.project_id,
            type=draft.type,
            title=draft.title,
            description=draft.description,
            priority=draft.priority,
            parent_id=issue.id,
            reporter_id=series.reporter_id,
            assignee_id=draft.assignee_id,
            start_at=start_at,
            due_at=due_at,
        )
        if draft.labels:
            label_service.set_issue_labels(
                session,
                created.id,
                draft.labels,
                actor_name=actor_name,
            )
        return
    start_days, start_minute = complete_offset_pair(
        draft.start_offset_days,
        draft.start_minute_of_day,
    )
    due_days, due_minute = complete_offset_pair(
        draft.due_offset_days,
        draft.due_minute_of_day,
    )
    check_recipe_window(start_days, start_minute, due_days, due_minute)
    item = SeriesItem(
        series_id=series.id,
        parent_item_id=issue.series_item_id,
        position=_next_position(session, series.id, issue.series_item_id),
        title=_clean_title(draft.title),
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
    if draft.labels:
        label_service.set_series_item_labels(session, item.id, draft.labels)
    windows = _open_windows(session, series.project_id)
    cutoff = issue.occurrence_on
    for copy in _copies(session, series.id):
        if copy.series_item_id != issue.series_item_id:
            continue
        if copy.occurrence_on is None or copy.status in CLOSED_STATUSES:
            continue
        if scope is EditScope.FUTURE and (
            cutoff is None or copy.occurrence_on < cutoff
        ):
            continue
        _spawn_item(session, series, item, copy.occurrence_on, copy, windows)


def _remove_tree_item(
    session: Session,
    issue: Issue,
    series: Series,
    scope: EditScope,
) -> None:
    if issue.series_item_id is None:
        raise InvalidSeriesError(
            "The root stays with the schedule. Delete the schedule to end it.",
        )
    if scope is EditScope.THIS:
        issue_service.delete_issue(session, issue.id)
        return
    item = session.get(SeriesItem, issue.series_item_id)
    if item is None or item.removed:
        raise InvalidSeriesError("That schedule item is gone.")
    ids = series_tree.descendant_ids(session, item)
    for row in session.scalars(select(SeriesItem).where(SeriesItem.id.in_(ids))).all():
        row.removed = True
    cutoff = issue.occurrence_on
    doomed = []
    for copy in _copies(session, series.id):
        if copy.series_item_id not in ids or copy.status in CLOSED_STATUSES:
            continue
        if scope is EditScope.FUTURE and (
            cutoff is None or copy.occurrence_on is None or copy.occurrence_on < cutoff
        ):
            continue
        doomed.append(copy)
    _delete_members(session, doomed)


def _apply_item_edit(
    session: Session,
    issue: Issue,
    series: Series,
    scope: EditScope,
    *,
    title: str | None,
    description: str | None,
    type: IssueType | None,
    priority: IssuePriority | None,
    assignee_id: int | None | object,
    spawn_mode: SeriesSpawnMode | None,
    sprint_basis: SeriesSprintBasis | None,
    look_ahead_n: int | None,
    freq: RecurrenceFreq | None,
    interval: int | None,
    weekdays: tuple[int, ...] | None,
    month_day: int | None | object,
    nth_week: int | None | object,
    month: int | None | object,
    starts_on: date | None,
    ends_on: date | None | object,
    occurrence_count: int | None | object,
    start_offset_days: int | None | object,
    start_minute_of_day: int | None | object,
    due_offset_days: int | None | object,
    due_minute_of_day: int | None | object,
    start_at: datetime | None | object,
    due_at: datetime | None | object,
    labels: Sequence[str] | None,
    today: date | None,
    actor_name: str | None,
) -> Issue:
    item = session.get(SeriesItem, issue.series_item_id)
    if item is None or item.removed:
        raise InvalidSeriesError("That schedule item is gone.")
    if start_at is not UNSET or due_at is not UNSET:
        start_offset_days, start_minute_of_day, due_offset_days, due_minute_of_day = (
            _offsets_from_datetimes(issue, start_at, due_at)
        )
    if title is not None:
        item.title = _clean_title(title)
    if description is not None:
        item.description = description.strip()
    if type is not None and type is not item.type:
        parent_type = series.type
        if item.parent_item_id is not None:
            parent = session.get(SeriesItem, item.parent_item_id)
            if parent is None:
                raise InvalidSeriesError("Choose a parent in this schedule.")
            parent_type = parent.type
        series_tree.require_child(type, parent_type)
        child_types = [
            row.type
            for row in series_tree.active_items(session, series.id)
            if row.parent_item_id == item.id
        ]
        series_tree.assert_children_of(type, child_types)
        item.type = type
    if priority is not None:
        item.priority = priority
    if assignee_id is not UNSET:
        item.assignee_id = assignee_id  # type: ignore[assignment]
    _assign_item_start(item, start_offset_days, start_minute_of_day)
    _assign_item_due(item, due_offset_days, due_minute_of_day)
    check_recipe_window(
        item.start_offset_days,
        item.start_minute_of_day,
        item.due_offset_days,
        item.due_minute_of_day,
    )
    if labels is not None:
        label_service.set_series_item_labels(session, item.id, labels)
    cutoff = issue.occurrence_on
    update_series(
        session,
        series.id,
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
        rewrite_from=cutoff if scope is EditScope.FUTURE else None,
        today=today,
    )
    for copy in _copies(session, series.id):
        if copy.series_item_id != item.id:
            continue
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
            priority=priority,
            assignee_id=assignee_id,
            parent_id=UNSET,
            labels=labels,
            actor_name=actor_name,
        )
        if copy.occurrence_on is not None:
            copy_start, copy_due = _item_window(item, copy.occurrence_on)
            issue_service.update_issue(
                session,
                copy.id,
                start_at=copy_start,
                due_at=copy_due,
                actor_name=actor_name,
            )
    return issue


def _assign_item_start(
    item: SeriesItem,
    offset_days: int | None | object,
    minute_of_day: int | None | object,
) -> None:
    if offset_days is UNSET and minute_of_day is UNSET:
        return
    item.start_offset_days, item.start_minute_of_day = complete_offset_pair(
        _merged_offset(offset_days, item.start_offset_days),
        _merged_offset(minute_of_day, item.start_minute_of_day),
    )


def _assign_item_due(
    item: SeriesItem,
    offset_days: int | None | object,
    minute_of_day: int | None | object,
) -> None:
    if offset_days is UNSET and minute_of_day is UNSET:
        return
    item.due_offset_days, item.due_minute_of_day = complete_offset_pair(
        _merged_offset(offset_days, item.due_offset_days),
        _merged_offset(minute_of_day, item.due_minute_of_day),
    )


def _next_position(
    session: Session,
    series_id: int,
    parent_item_id: int | None,
) -> int:
    siblings = [
        item.position
        for item in series_tree.active_items(session, series_id)
        if item.parent_item_id == parent_item_id
    ]
    if not siblings:
        return 0
    return max(siblings) + 1


def _delete_members(session: Session, members: Sequence[Issue]) -> None:
    remaining = list(members)
    while remaining:
        leaves = [
            item
            for item in remaining
            if all(other.parent_id != item.id for other in remaining)
        ]
        if not leaves:
            raise InvalidSeriesError("This occurrence could not be removed.")
        gone = {item.id for item in leaves}
        for leaf in leaves:
            session.delete(leaf)
        session.flush()
        remaining = [item for item in remaining if item.id not in gone]
