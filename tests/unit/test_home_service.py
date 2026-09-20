from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import IssueHistory, Project
from keel.domain.enums import (
    DependencyKind,
    IssueStatus,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
)
from keel.services import dependencies as dependency_service
from keel.services import history as history_service
from keel.services import home as home_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service

TODAY = date(2026, 9, 13)
TODAY_NOON = datetime(2026, 9, 13, 12, 0)
YESTERDAY_NOON = datetime(2026, 9, 12, 12, 0)


def _project(session: Session, key: str = "KEEL") -> Project:
    return project_service.create_project(session, key, key.title())


def _complete_on(session: Session, issue_id: int, when: datetime) -> None:
    issue_service.update_issue(session, issue_id, status=IssueStatus.DONE)
    event = session.scalars(
        select(IssueHistory)
        .where(
            IssueHistory.issue_id == issue_id,
            IssueHistory.field == history_service.FIELD_STATUS,
            IssueHistory.to_value == "Done",
        )
        .order_by(IssueHistory.id.desc()),
    ).first()
    assert event is not None
    event.created_at = when
    session.flush()


def test_unassigned_and_other_people_stay_off_the_inbox(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Mine",
        assignee_id=ada.id,
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Unassigned",
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Grace's",
        assignee_id=grace.id,
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.title for item in inbox.assigned] == ["Mine"]
    assert inbox.empty is False


def test_assigned_is_unfinished_work_across_projects(session: Session) -> None:
    keel = _project(session, "KEEL")
    site = _project(session, "SITE")
    ada = user_service.create_user(session, "Ada")
    later = issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Later",
        assignee_id=ada.id,
    )
    first = issue_service.create_issue(
        session,
        site.id,
        IssueType.STORY,
        "First",
        assignee_id=ada.id,
    )
    done = issue_service.create_issue(
        session,
        keel.id,
        IssueType.STORY,
        "Finished",
        assignee_id=ada.id,
    )
    issue_service.update_issue(session, done.id, status=IssueStatus.DONE)

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.key for item in inbox.assigned] == ["KEEL-1", "SITE-1"]
    assert {item.issue.id for item in inbox.assigned} == {later.id, first.id}


def test_upcoming_is_after_today_through_week_or_month_end(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Overdue",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 12, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Due today",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 13, 23, 0),
    )
    later_this_month = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Later this month",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 30, 8, 0),
    )
    next_week_this_month = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Next Monday",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 14, 8, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Next month",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 1, 8, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "No date",
        assignee_id=ada.id,
    )
    closed = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Closed upcoming",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 20, 8, 0),
    )
    issue_service.update_issue(session, closed.id, status=IssueStatus.DONE)

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.upcoming] == [
        next_week_this_month.id,
        later_this_month.id,
    ]
    assert {item.issue.title for item in inbox.due} == {"Overdue", "Due today"}
    assert closed.id not in {item.issue.id for item in inbox.upcoming}


def test_upcoming_includes_next_month_when_the_iso_week_spills(
    session: Session,
) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    spilled = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Next month this week",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 2, 9, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "After the week",
        assignee_id=ada.id,
        due_at=datetime(2026, 10, 5, 9, 0),
    )

    inbox = home_service.personal_inbox(session, ada.id, today=date(2026, 9, 30))

    assert [item.issue.id for item in inbox.upcoming] == [spilled.id]


def test_an_inbox_of_only_upcoming_is_not_empty(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    soon = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Later this month",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 20, 9, 0),
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert inbox.empty is False
    assert inbox.due == ()
    assert [item.issue.id for item in inbox.upcoming] == [soon.id]


def test_horizon_end_is_the_later_of_iso_week_and_month() -> None:
    assert home_service._horizon_end(date(2026, 9, 13)) == date(2026, 9, 30)
    assert home_service._horizon_end(date(2026, 9, 16)) == date(2026, 9, 30)
    assert home_service._horizon_end(date(2026, 9, 30)) == date(2026, 10, 4)


def test_due_is_today_or_earlier_by_calendar_date(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    overdue = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Overdue",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 12, 9, 0),
    )
    due_today = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Due today",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 13, 23, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Tomorrow",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 14, 8, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "No date",
        assignee_id=ada.id,
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.due] == [overdue.id, due_today.id]
    assert {item.issue.title for item in inbox.assigned} >= {
        "Overdue",
        "Due today",
        "Tomorrow",
        "No date",
    }


def test_default_today_is_local_date_so_utc_tomorrow_stays_out(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    due_today = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Due today",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 16, 23, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Tomorrow",
        assignee_id=ada.id,
        due_at=datetime(2026, 9, 17, 0, 0),
    )

    class LocalDate(date):
        @classmethod
        def today(cls) -> "LocalDate":
            return cls(2026, 9, 16)

    monkeypatch.setattr(home_service, "date", LocalDate)
    inbox = home_service.personal_inbox(session, ada.id)

    assert [item.issue.id for item in inbox.due] == [due_today.id]


def test_starting_is_today_or_earlier_by_calendar_date(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    started = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Started",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 12, 9, 0),
    )
    starts_today = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Starts today",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 13, 23, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Tomorrow",
        assignee_id=ada.id,
        start_at=datetime(2026, 9, 14, 8, 0),
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "No start",
        assignee_id=ada.id,
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.starting] == [started.id, starts_today.id]


def test_blocked_is_status_or_unresolved_blockers(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    marked = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Marked blocked",
        assignee_id=ada.id,
    )
    issue_service.update_issue(session, marked.id, status=IssueStatus.BLOCKED)
    waiting = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Waiting on a link",
        assignee_id=ada.id,
    )
    blocker = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Blocker",
        assignee_id=ada.id,
    )
    dependency_service.create_dependency(
        session,
        blocker.id,
        waiting.id,
        DependencyKind.BLOCKS,
    )
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Clear",
        assignee_id=ada.id,
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.title for item in inbox.blocked] == [
        "Marked blocked",
        "Waiting on a link",
    ]
    assert inbox.blocked[1].unresolved_blockers == 1


def test_active_sprint_includes_closed_items(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    active = sprint_service.create_sprint(session, project.id, "This week")
    planned = sprint_service.create_sprint(session, project.id, "Next")
    sprint_service.start_sprint(session, active.id)
    open_item = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "In flight",
        assignee_id=ada.id,
        sprint_id=active.id,
    )
    done = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Shipped",
        assignee_id=ada.id,
        sprint_id=active.id,
    )
    issue_service.update_issue(session, done.id, status=IssueStatus.DONE)
    issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Planned only",
        assignee_id=ada.id,
        sprint_id=planned.id,
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.active_sprint] == [open_item.id, done.id]
    assert done.id not in {item.issue.id for item in inbox.assigned}
    assert {item.sprint_name for item in inbox.active_sprint} == {"This week"}


def test_waiting_this_cycle_excludes_future_look_ahead(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    series = series_service.create_series(
        session,
        project.id,
        title="Chore",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.CALENDAR,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.MONTHLY,
        starts_on=date(2026, 10, 1),
        month_day=1,
        look_ahead_n=1,
        assignee_id=ada.id,
        today=TODAY,
    )
    current = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "This cycle",
        assignee_id=ada.id,
        series_id=series.id,
        occurrence_on=date(2026, 9, 1),
    )
    closed = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Last cycle done",
        assignee_id=ada.id,
        series_id=series.id,
        occurrence_on=date(2026, 8, 1),
    )
    issue_service.update_issue(session, closed.id, status=IssueStatus.DONE)

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.waiting] == [current.id]
    for item in inbox.waiting:
        assert item.issue.occurrence_on is not None
        assert item.issue.occurrence_on <= TODAY


def test_completed_today_is_done_assigned_work_moved_today(
    session: Session,
) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    finished = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Shipped today",
        assignee_id=ada.id,
    )
    _complete_on(session, finished.id, TODAY_NOON)
    yesterday = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Shipped yesterday",
        assignee_id=ada.id,
    )
    _complete_on(session, yesterday.id, YESTERDAY_NOON)
    issue_service.update_issue(session, yesterday.id, title="Edited after done")
    cancelled = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Dropped",
        assignee_id=ada.id,
    )
    issue_service.update_issue(session, cancelled.id, status=IssueStatus.CANCELLED)
    reopened = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Reopened",
        assignee_id=ada.id,
    )
    _complete_on(session, reopened.id, TODAY_NOON)
    issue_service.update_issue(session, reopened.id, status=IssueStatus.IN_PROGRESS)
    unassigned = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "No owner",
    )
    _complete_on(session, unassigned.id, TODAY_NOON)
    grace_item = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Grace shipped",
        assignee_id=grace.id,
    )
    _complete_on(session, grace_item.id, TODAY_NOON)
    still_open = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Still open",
        assignee_id=ada.id,
    )

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.completed] == [finished.id]
    assert inbox.completed[0].completed_at == TODAY_NOON
    assert still_open.id in {item.issue.id for item in inbox.assigned}
    assert finished.id not in {item.issue.id for item in inbox.assigned}


def test_created_as_done_counts_as_completed_on_the_birth_day(
    session: Session,
) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    born_done = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Filed closed",
        status=IssueStatus.DONE,
        assignee_id=ada.id,
    )
    born_done.created_at = TODAY_NOON
    session.flush()

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.completed] == [born_done.id]
    assert inbox.completed[0].completed_at == TODAY_NOON


def test_completed_today_sorts_newest_first(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    earlier = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Morning",
        assignee_id=ada.id,
    )
    later = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Afternoon",
        assignee_id=ada.id,
    )
    _complete_on(session, earlier.id, datetime(2026, 9, 13, 9, 0))
    _complete_on(session, later.id, datetime(2026, 9, 13, 16, 0))

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.title for item in inbox.completed] == ["Afternoon", "Morning"]


def test_completed_today_can_overlap_the_active_sprint(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    active = sprint_service.create_sprint(session, project.id, "This week")
    sprint_service.start_sprint(session, active.id)
    shipped = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Sprint done",
        assignee_id=ada.id,
        sprint_id=active.id,
    )
    _complete_on(session, shipped.id, TODAY_NOON)

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert [item.issue.id for item in inbox.completed] == [shipped.id]
    assert shipped.id in {item.issue.id for item in inbox.active_sprint}


def test_an_inbox_of_only_completed_today_is_not_empty(session: Session) -> None:
    project = _project(session)
    ada = user_service.create_user(session, "Ada")
    finished = issue_service.create_issue(
        session,
        project.id,
        IssueType.STORY,
        "Only this",
        assignee_id=ada.id,
    )
    _complete_on(session, finished.id, TODAY_NOON)

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert inbox.empty is False
    assert inbox.assigned == ()
    assert [item.issue.id for item in inbox.completed] == [finished.id]


def test_an_empty_inbox_has_no_sections(session: Session) -> None:
    ada = user_service.create_user(session, "Ada")
    _project(session)

    inbox = home_service.personal_inbox(session, ada.id, today=TODAY)

    assert inbox.empty is True
    assert inbox.assigned == ()
    assert inbox.due == ()
    assert inbox.upcoming == ()
    assert inbox.blocked == ()
    assert inbox.active_sprint == ()
    assert inbox.waiting == ()
    assert inbox.completed == ()


def test_aware_due_timestamps_use_the_utc_calendar_day() -> None:
    late = datetime(2026, 9, 13, 23, 0, tzinfo=UTC)
    assert home_service._calendar_day(late) == date(2026, 9, 13)
    naive = home_service._as_naive_utc(late)
    assert naive.tzinfo is None
    assert naive == datetime(2026, 9, 13, 23, 0)
