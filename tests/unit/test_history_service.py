from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import (
    IssuePriority,
    IssueStatus,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SprintCadence,
)
from keel.domain.errors import NotFoundError
from keel.services import auto_sprint
from keel.services import history as history_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import series as series_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.identity import bind_acting_user, reset_acting_user


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _story(session: Session, project: Project, **kwargs: object) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Something",
        **kwargs,  # type: ignore[arg-type]
    ).id


def test_labels_for_missing_rows_match_empty_copy(
    session: Session,
) -> None:
    assert history_service.assignee_label(session, 999) == "Unassigned"
    assert history_service.sprint_label(session, 999) == "Unscheduled"
    assert history_service.parent_label(session, 999) == "No parent"
    assert history_service.text_label("") == "none"
    assert history_service.text_label("  ") == "none"
    assert history_service.text_label("A note") == "A note"
    assert history_service.labels_label(()) == "none"
    assert history_service.labels_label(("urgent", "bug")) == "bug, urgent"


def test_a_new_issue_has_no_history(session: Session, project: Project) -> None:
    issue_id = _story(session, project)
    assert list(history_service.list_history(session, issue_id)) == []


def test_status_change_records_who_when_from_to(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        status=IssueStatus.IN_PROGRESS,
        actor_name="Ada",
    )

    events = history_service.list_history(session, issue_id)
    assert len(events) == 1
    event = events[0]
    assert event.actor_name == "Ada"
    assert event.field == "status"
    assert event.from_value == "To Do"
    assert event.to_value == "In Progress"


def test_a_noop_status_save_does_not_append(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        status=IssueStatus.TODO,
        actor_name="Ada",
    )
    assert list(history_service.list_history(session, issue_id)) == []


def test_title_and_description_are_recorded(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        title="Renamed",
        description="A note",
        actor_name="Ada",
    )
    events = history_service.list_history(session, issue_id)
    assert [(event.field, event.from_value, event.to_value) for event in events] == [
        ("title", "Something", "Renamed"),
        ("description", "none", "A note"),
    ]
    assert {event.actor_name for event in events} == {"Ada"}


def test_priority_change_is_recorded(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        priority=IssuePriority.P1,
        actor_name="Ada",
    )
    events = history_service.list_history(session, issue_id)
    assert len(events) == 1
    event = events[0]
    assert event.actor_name == "Ada"
    assert event.field == "priority"
    assert event.from_value == "P3 — Major"
    assert event.to_value == "P1 — Blocker"


def test_a_noop_priority_save_does_not_append(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        priority=IssuePriority.P3,
        actor_name="Ada",
    )
    assert list(history_service.list_history(session, issue_id)) == []


def test_a_noop_title_and_description_save_does_not_append(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        title="Renamed",
        description="A note",
        actor_name="Ada",
    )
    issue_service.update_issue(
        session,
        issue_id,
        title="Renamed",
        description="A note",
        actor_name="Ada",
    )
    assert len(history_service.list_history(session, issue_id)) == 2


def test_cleared_description_says_none(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project, description="A note")
    issue_service.update_issue(
        session,
        issue_id,
        description="",
        actor_name="Ada",
    )
    events = history_service.list_history(session, issue_id)
    assert len(events) == 1
    assert events[0].field == "description"
    assert events[0].from_value == "A note"
    assert events[0].to_value == "none"


def test_several_fields_append_several_lines(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    ada = user_service.create_user(session, "Ada")
    issue_service.update_issue(
        session,
        issue_id,
        status=IssueStatus.IN_REVIEW,
        assignee_id=ada.id,
        estimate_minutes=120,
        remaining_minutes=90,
        actor_name="Ada",
    )
    events = history_service.list_history(session, issue_id)
    assert [(event.field, event.from_value, event.to_value) for event in events] == [
        ("status", "To Do", "In Review"),
        ("assignee", "Unassigned", "Ada"),
        ("estimate", "none", "2h"),
        ("remaining", "none", "1h 30m"),
    ]
    assert {event.actor_name for event in events} == {"Ada"}


def test_cleared_due_parent_and_type_use_issue_page_labels(
    session: Session,
    project: Project,
) -> None:
    epic = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.EPIC,
        title="Epic",
    ).id
    story = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Child",
        parent_id=epic,
        due_at=datetime(2026, 9, 14, 15, 0),
    )
    issue_service.update_issue(
        session,
        story.id,
        parent_id=None,
        due_at=None,
        actor_name="Ada",
    )
    issue_service.update_issue(
        session,
        story.id,
        type=IssueType.SUBTASK,
        actor_name="Ada",
    )
    events = history_service.list_history(session, story.id)
    by_field = {event.field: (event.from_value, event.to_value) for event in events}
    assert by_field["parent"] == ("KEEL-1", "No parent")
    assert by_field["due date"] == ("2026-09-14 15:00 UTC", "none")
    assert by_field["type"] == ("Story", "Subtask")


def test_renaming_a_user_does_not_rewrite_old_lines(
    session: Session,
    project: Project,
) -> None:
    ada = user_service.create_user(session, "Ada")
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        assignee_id=ada.id,
        actor_name="Ada",
    )
    user_service.rename_user(session, ada.id, "Ada Lovelace")
    events = history_service.list_history(session, issue_id)
    assert events[0].to_value == "Ada"
    assert events[0].actor_name == "Ada"


def test_history_is_oldest_first(session: Session, project: Project) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        status=IssueStatus.IN_PROGRESS,
        actor_name="Ada",
    )
    issue_service.update_issue(
        session,
        issue_id,
        status=IssueStatus.DONE,
        actor_name="Ada",
    )
    events = history_service.list_history(session, issue_id)
    assert [event.to_value for event in events] == ["In Progress", "Done"]


def test_deleting_an_issue_cascades_its_history(
    session: Session,
    project: Project,
) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(
        session,
        issue_id,
        status=IssueStatus.BLOCKED,
        actor_name="Ada",
    )
    issue_service.delete_issue(session, issue_id)
    session.expire_all()
    with pytest.raises(NotFoundError):
        history_service.list_history(session, issue_id)


def test_unbound_actor_is_keel(session: Session, project: Project) -> None:
    issue_id = _story(session, project)
    issue_service.update_issue(session, issue_id, status=IssueStatus.IN_PROGRESS)
    events = history_service.list_history(session, issue_id)
    assert events[0].actor_name == history_service.SYSTEM_ACTOR


def test_bound_actor_names_the_picker(session: Session, project: Project) -> None:
    ada = user_service.create_user(session, "Ada")
    token = bind_acting_user(ada)
    try:
        issue_id = _story(session, project)
        issue_service.update_issue(session, issue_id, status=IssueStatus.IN_PROGRESS)
    finally:
        reset_acting_user(token)
    events = history_service.list_history(session, issue_id)
    assert events[0].actor_name == "Ada"


def test_sprint_complete_records_carry_over(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Sprint 3")
    later = sprint_service.create_sprint(session, project.id, "Sprint 4")
    issue_id = _story(session, project, sprint_id=current.id)
    sprint_service.start_sprint(session, current.id)

    sprint_service.complete_sprint(session, current.id, actor_name="Ada")

    events = history_service.list_history(session, issue_id)
    assert len(events) == 1
    assert events[0].actor_name == "Ada"
    assert events[0].field == "sprint"
    assert events[0].from_value == "Sprint 3"
    assert events[0].to_value == "Sprint 4"
    assert issue_service.get_issue(session, issue_id).sprint_id == later.id


def test_sprint_complete_to_the_backlog_says_unscheduled(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Now")
    issue_id = _story(session, project, sprint_id=current.id)
    sprint_service.start_sprint(session, current.id)
    sprint_service.complete_sprint(session, current.id, actor_name="Ada")
    events = history_service.list_history(session, issue_id)
    assert events[0].to_value == "Unscheduled"


def test_series_claim_records_keel(
    session: Session,
    project: Project,
) -> None:
    series = series_service.create_series(
        session,
        project.id,
        title="Take out trash",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.CALENDAR,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.WEEKLY,
        starts_on=date(2026, 9, 14),
        weekdays=(0,),
        look_ahead_n=1,
        today=date(2026, 9, 12),
    )
    copies = [
        issue
        for issue in issue_service.list_issues(session, project.id)
        if issue.series_id == series.id
    ]
    assert len(copies) == 1
    claimed = copies[0]
    assert claimed.sprint_id is None
    window = sprint_service.create_sprint(
        session,
        project.id,
        name="This week",
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 18),
    )
    series_service.advance_series(session, series.id, date(2026, 9, 12))
    events = history_service.list_history(session, claimed.id)
    assert len(events) == 1
    assert events[0].actor_name == "Keel"
    assert events[0].field == "sprint"
    assert events[0].from_value == "Unscheduled"
    assert events[0].to_value == window.name
    assert issue_service.get_issue(session, claimed.id).sprint_id == window.id


def test_auto_sprint_rollover_records_keel(
    session: Session,
    project: Project,
) -> None:
    today = date(2026, 9, 12)
    auto_sprint.apply_cadence(session, project, SprintCadence.WEEKLY, None, today)
    first = sprint_service.active_sprint(session, project.id)
    assert first is not None
    issue_id = _story(session, project, sprint_id=first.id)

    auto_sprint.advance_all(session, date(2026, 10, 10))

    events = history_service.list_history(session, issue_id)
    assert len(events) == 1
    assert events[0].actor_name == "Keel"
    assert events[0].field == "sprint"
    assert events[0].from_value == first.name
    assert events[0].to_value != "Unscheduled"
