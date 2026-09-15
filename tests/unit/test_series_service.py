from datetime import date

import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project, Series
from keel.domain.enums import (
    EditScope,
    IssueStatus,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
)
from keel.domain.errors import (
    InvalidSeriesError,
    NotFoundError,
    SeriesStoppedError,
)
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import sprints as sprint_service
from keel.services.issues import IssueFilters


def _project(session: Session) -> Project:
    return project_service.create_project(session, "HOME", "Home")


def _weekly(
    session: Session,
    project: Project,
    **kwargs: object,
) -> Series:
    payload: dict[str, object] = {
        "title": "Take out trash",
        "type": IssueType.STORY,
        "spawn_mode": SeriesSpawnMode.CALENDAR,
        "sprint_basis": SeriesSprintBasis.DUE_ON,
        "freq": RecurrenceFreq.WEEKLY,
        "starts_on": date(2026, 9, 14),
        "weekdays": (0,),
        "look_ahead_n": 1,
        "today": date(2026, 9, 12),
    }
    payload.update(kwargs)
    return series_service.create_series(session, project.id, **payload)  # type: ignore[arg-type]


def test_calendar_mode_spawns_into_an_overlapping_sprint(
    session: Session,
) -> None:
    project = _project(session)
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        name="12–18 Sep",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    sprint_service.start_sprint(session, sprint.id)
    series = _weekly(session, project)
    copies = issue_service.list_issues(session, project.id)
    in_sprint = [issue for issue in copies if issue.sprint_id == sprint.id]
    unscheduled = [
        issue
        for issue in copies
        if issue.series_id == series.id and issue.sprint_id is None
    ]
    assert len(in_sprint) == 1
    assert in_sprint[0].occurrence_on == date(2026, 9, 14)
    assert len(unscheduled) == 1
    assert unscheduled[0].occurrence_on == date(2026, 9, 21)
    series_service.advance_series(session, series.id, date(2026, 9, 12))
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    assert len(copies) == 2


def test_created_on_does_not_fill_the_current_sprint_with_future_cycles(
    session: Session,
) -> None:
    project = _project(session)
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        name="This week",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    sprint_service.start_sprint(session, sprint.id)
    _weekly(
        session,
        project,
        sprint_basis=SeriesSprintBasis.CREATED_ON,
        today=date(2026, 9, 12),
    )
    assert issue_service.list_issues(session, project.id) == []
    series_service.advance_all(session, date(2026, 9, 14))
    copies = issue_service.list_issues(session, project.id)
    assert len(copies) == 1
    assert copies[0].occurrence_on == date(2026, 9, 14)
    assert copies[0].sprint_id == sprint.id


def test_after_closed_skips_missed_cycles_and_does_not_stack(
    session: Session,
) -> None:
    project = _project(session)
    series = series_service.create_series(
        session,
        project.id,
        title="Pay bills",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.AFTER_CLOSED,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.WEEKLY,
        starts_on=date(2026, 9, 7),
        weekdays=(0,),
        today=date(2026, 9, 7),
    )
    first = issue_service.list_issues(session, project.id)[0]
    assert first.series_id == series.id
    first.status = IssueStatus.CANCELLED
    session.flush()
    # Pretend three weeks passed; closing should spawn next-from-now, not backfill.
    series_service.advance_series(session, series.id, date(2026, 9, 28))
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    open_copies = [
        issue for issue in copies if issue.status is not IssueStatus.CANCELLED
    ]
    assert len(open_copies) == 1
    assert open_copies[0].occurrence_on == date(2026, 9, 28)


def test_an_unfinished_after_closed_copy_carries_without_a_second_spawn(
    session: Session,
) -> None:
    project = _project(session)
    current = sprint_service.create_sprint(
        session,
        project.id,
        name="This week",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    nxt = sprint_service.create_sprint(
        session,
        project.id,
        name="Next week",
        starts_on=date(2026, 9, 19),
        ends_on=date(2026, 9, 25),
    )
    sprint_service.start_sprint(session, current.id)
    series = _weekly(
        session,
        project,
        spawn_mode=SeriesSpawnMode.AFTER_CLOSED,
        look_ahead_n=1,
        today=date(2026, 9, 14),
    )
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    assert len(copies) == 1
    sprint_service.complete_sprint(session, current.id)
    sprint_service.start_sprint(session, nxt.id)
    series_service.advance_series(session, series.id, date(2026, 9, 21))
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    assert len(copies) == 1
    assert copies[0].sprint_id == nxt.id


def test_calendar_mode_also_spawns_the_new_window_after_rollover(
    session: Session,
) -> None:
    project = _project(session)
    current = sprint_service.create_sprint(
        session,
        project.id,
        name="This week",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    nxt = sprint_service.create_sprint(
        session,
        project.id,
        name="Next week",
        starts_on=date(2026, 9, 19),
        ends_on=date(2026, 9, 25),
    )
    sprint_service.start_sprint(session, current.id)
    series = _weekly(
        session,
        project,
        sprint_basis=SeriesSprintBasis.CREATED_ON,
        today=date(2026, 9, 14),
    )
    sprint_service.complete_sprint(session, current.id)
    sprint_service.start_sprint(session, nxt.id)
    series_service.advance_series(session, series.id, date(2026, 9, 21))
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    dates = {issue.occurrence_on for issue in copies}
    assert date(2026, 9, 14) in dates
    assert date(2026, 9, 21) in dates
    carried = [issue for issue in copies if issue.occurrence_on == date(2026, 9, 14)]
    born = [issue for issue in copies if issue.occurrence_on == date(2026, 9, 21)]
    assert carried[0].sprint_id == nxt.id
    assert born[0].sprint_id == nxt.id


def test_a_completed_sprint_is_not_used_for_spawn(
    session: Session,
) -> None:
    project = _project(session)
    past = sprint_service.create_sprint(
        session,
        project.id,
        name="Done week",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    sprint_service.start_sprint(session, past.id)
    sprint_service.complete_sprint(session, past.id)
    series = _weekly(session, project, today=date(2026, 9, 14))
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    assert copies
    assert all(issue.sprint_id is None for issue in copies)


def test_deleting_an_occurrence_does_not_respawn_that_date(
    session: Session,
) -> None:
    project = _project(session)
    series_service.create_series(
        session,
        project.id,
        title="Trash",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.CALENDAR,
        sprint_basis=SeriesSprintBasis.CREATED_ON,
        freq=RecurrenceFreq.WEEKLY,
        starts_on=date(2026, 9, 14),
        weekdays=(0,),
        today=date(2026, 9, 14),
    )
    copies = issue_service.list_issues(session, project.id)
    assert len(copies) == 1
    issue_service.delete_issue(session, copies[0].id)
    series_service.advance_all(session, date(2026, 9, 14))
    assert issue_service.list_issues(session, project.id) == []


def test_pause_stops_new_copies_and_claiming_assigns_a_preview(
    session: Session,
) -> None:
    project = _project(session)
    series = _weekly(session, project)
    preview = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(unscheduled=True),
    )[0]
    series_service.set_state(session, series.id, SeriesState.PAUSED)
    before = len(issue_service.list_issues(session, project.id))
    series_service.advance_series(session, series.id, date(2026, 9, 21))
    assert len(issue_service.list_issues(session, project.id)) == before
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        name="This week",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    sprint_service.start_sprint(session, sprint.id)
    series_service.set_state(
        session,
        series.id,
        SeriesState.ACTIVE,
        today=date(2026, 9, 12),
    )
    session.refresh(preview)
    assert preview.sprint_id == sprint.id


def test_stop_leaves_existing_issues_and_cannot_resume(
    session: Session,
) -> None:
    project = _project(session)
    series = _weekly(session, project)
    before = len(issue_service.list_issues(session, project.id))
    series_service.set_state(session, series.id, SeriesState.STOPPED)
    series_service.advance_series(session, series.id, date(2026, 9, 28))
    assert len(issue_service.list_issues(session, project.id)) == before
    with pytest.raises(SeriesStoppedError):
        series_service.set_state(session, series.id, SeriesState.ACTIVE)
    with pytest.raises(SeriesStoppedError):
        series_service.update_series(session, series.id, title="Later trash")


def test_outlook_scopes_change_this_copy_or_the_recipe(
    session: Session,
) -> None:
    project = _project(session)
    series = _weekly(session, project, look_ahead_n=2)
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    copies.sort(key=lambda issue: issue.occurrence_on or date.min)
    first, second = copies[0], copies[1]
    series_service.apply_occurrence_edit(
        session,
        first.id,
        EditScope.THIS,
        title="Only this week",
    )
    session.refresh(series)
    session.refresh(second)
    assert first.title == "Only this week"
    assert series.title == "Take out trash"
    assert second.title == "Take out trash"
    series_service.apply_occurrence_edit(
        session,
        second.id,
        EditScope.FUTURE,
        title="From here on",
    )
    session.refresh(series)
    session.refresh(first)
    session.refresh(second)
    assert series.title == "From here on"
    assert first.title == "Only this week"
    assert second.title == "From here on"
    series_service.apply_occurrence_edit(
        session,
        first.id,
        EditScope.SERIES,
        title="Whole series",
    )
    session.refresh(series)
    session.refresh(first)
    session.refresh(second)
    assert series.title == "Whole series"
    assert first.title == "Whole series"
    assert second.title == "Whole series"


def test_closing_an_ended_after_closed_series_does_not_spawn(
    session: Session,
) -> None:
    project = _project(session)
    series = series_service.create_series(
        session,
        project.id,
        title="Once",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.AFTER_CLOSED,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.DAILY,
        starts_on=date(2026, 9, 12),
        occurrence_count=1,
        today=date(2026, 9, 12),
    )
    issue = issue_service.list_issues(session, project.id)[0]
    issue_service.update_issue(session, issue.id, status=IssueStatus.DONE)
    copies = [
        row
        for row in issue_service.list_issues(session, project.id)
        if row.series_id == series.id
    ]
    assert len(copies) == 1


def test_seed_must_be_a_plain_issue_in_the_same_project(
    session: Session,
) -> None:
    home = _project(session)
    other = project_service.create_project(session, "WORK", "Work")
    foreign = issue_service.create_issue(
        session,
        other.id,
        type=IssueType.STORY,
        title="Elsewhere",
    )
    local = issue_service.create_issue(
        session,
        home.id,
        type=IssueType.STORY,
        title="Pay bills",
    )
    with pytest.raises(InvalidSeriesError):
        series_service.create_series(
            session,
            home.id,
            title="Pay bills",
            type=IssueType.STORY,
            spawn_mode=SeriesSpawnMode.AFTER_CLOSED,
            sprint_basis=SeriesSprintBasis.DUE_ON,
            freq=RecurrenceFreq.MONTHLY,
            starts_on=date(2026, 9, 1),
            month_day=1,
            seed_issue_id=foreign.id,
            today=date(2026, 9, 12),
        )
    series_service.create_series(
        session,
        home.id,
        title="Pay bills",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.AFTER_CLOSED,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.MONTHLY,
        starts_on=date(2026, 9, 1),
        month_day=1,
        seed_issue_id=local.id,
        today=date(2026, 9, 12),
    )
    with pytest.raises(InvalidSeriesError):
        series_service.create_series(
            session,
            home.id,
            title="Again",
            type=IssueType.STORY,
            spawn_mode=SeriesSpawnMode.CALENDAR,
            sprint_basis=SeriesSprintBasis.DUE_ON,
            freq=RecurrenceFreq.WEEKLY,
            starts_on=date(2026, 9, 14),
            seed_issue_id=local.id,
            today=date(2026, 9, 12),
        )


def test_series_validation_and_missing_rows(session: Session) -> None:
    project = _project(session)
    with pytest.raises(NotFoundError):
        series_service.get_series(session, 404)
    with pytest.raises(InvalidSeriesError):
        _weekly(session, project, title="  ")
    with pytest.raises(InvalidSeriesError):
        _weekly(session, project, look_ahead_n=0)
    issue = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="One-off",
    )
    issue_service.update_issue(session, issue.id, status=IssueStatus.IN_PROGRESS)
    with pytest.raises(InvalidSeriesError):
        series_service.apply_occurrence_edit(
            session,
            issue.id,
            EditScope.THIS,
            title="Nope",
        )


def test_deleting_the_same_occurrence_twice_is_idempotent(
    session: Session,
) -> None:
    project = _project(session)
    series = _weekly(
        session,
        project,
        sprint_basis=SeriesSprintBasis.CREATED_ON,
        today=date(2026, 9, 14),
    )
    copy = issue_service.list_issues(session, project.id)[0]
    occurrence = copy.occurrence_on
    assert occurrence is not None
    issue_service.delete_issue(session, copy.id)
    series_service.after_issue_deleted(
        session, series.id, occurrence, date(2026, 9, 14)
    )
    assert issue_service.list_issues(session, project.id) == []


def test_spawned_copies_get_start_and_due_from_offsets(
    session: Session,
) -> None:
    from datetime import datetime

    project = _project(session)
    series = _weekly(
        session,
        project,
        start_offset_days=-1,
        start_minute_of_day=9 * 60,
        due_offset_days=0,
        due_minute_of_day=17 * 60,
        sprint_basis=SeriesSprintBasis.CREATED_ON,
        today=date(2026, 9, 14),
    )
    copy = next(
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    )
    assert copy.occurrence_on == date(2026, 9, 14)
    assert copy.start_at == datetime(2026, 9, 13, 9, 0)
    assert copy.due_at == datetime(2026, 9, 14, 17, 0)


def test_start_sprint_basis_uses_the_start_calendar_date(
    session: Session,
) -> None:
    project = _project(session)
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        name="Early window",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 13),
    )
    sprint_service.start_sprint(session, sprint.id)
    series = _weekly(
        session,
        project,
        start_offset_days=-1,
        start_minute_of_day=9 * 60,
        due_offset_days=0,
        due_minute_of_day=17 * 60,
        sprint_basis=SeriesSprintBasis.START_ON,
        look_ahead_n=1,
        today=date(2026, 9, 12),
    )
    in_sprint = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id and issue.sprint_id == sprint.id
    ]
    assert len(in_sprint) == 1
    assert in_sprint[0].occurrence_on == date(2026, 9, 14)
    assert in_sprint[0].start_at is not None
    assert in_sprint[0].start_at.date() == date(2026, 9, 13)


def test_outlook_scopes_rewrite_open_copy_dates(
    session: Session,
) -> None:
    from datetime import datetime

    project = _project(session)
    series = _weekly(session, project, look_ahead_n=2)
    copies = sorted(
        [
            issue
            for issue in issue_service.list_issues(session, project.id)
            if issue.series_id == series.id
        ],
        key=lambda issue: issue.occurrence_on or date.min,
    )
    first, second = copies[0], copies[1]
    series_service.apply_occurrence_edit(
        session,
        first.id,
        EditScope.THIS,
        start_at=datetime(2026, 9, 13, 8, 0),
        due_at=datetime(2026, 9, 14, 18, 0),
    )
    session.refresh(second)
    session.refresh(series)
    assert first.start_at == datetime(2026, 9, 13, 8, 0)
    assert series.start_offset_days == 0
    assert second.start_at == datetime(2026, 9, 21, 0, 0)
    series_service.apply_occurrence_edit(
        session,
        second.id,
        EditScope.FUTURE,
        start_at=datetime(2026, 9, 20, 9, 0),
        due_at=datetime(2026, 9, 21, 17, 0),
    )
    session.refresh(series)
    session.refresh(first)
    session.refresh(second)
    assert series.start_offset_days == -1
    assert series.start_minute_of_day == 9 * 60
    assert series.due_minute_of_day == 17 * 60
    assert first.start_at == datetime(2026, 9, 13, 8, 0)
    assert second.start_at == datetime(2026, 9, 20, 9, 0)
    assert second.due_at == datetime(2026, 9, 21, 17, 0)
