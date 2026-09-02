from datetime import date

import pytest
from sqlalchemy.orm import Session

from keel.db.models import Project
from keel.domain.enums import IssueStatus, IssueType, SprintState
from keel.domain.errors import (
    InvalidSprintError,
    SprintAlreadyActiveError,
    SprintInvalidTransitionError,
    SprintProjectMismatchError,
)
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services.issues import IssueFilters


@pytest.fixture
def project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def issue_id(
    session: Session,
    project: Project,
    title: str = "Work",
    **kwargs: object,
) -> int:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title=title,
        **kwargs,  # type: ignore[arg-type]
    ).id


def test_a_sprint_starts_planned(session: Session, project: Project) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    assert sprint.state is SprintState.PLANNED
    assert sprint.goal == ""


def test_a_blank_name_is_refused(session: Session, project: Project) -> None:
    with pytest.raises(InvalidSprintError) as caught:
        sprint_service.create_sprint(session, project.id, "  ")
    assert caught.value.code == "sprint.invalid"


def test_an_end_before_the_start_is_refused(
    session: Session,
    project: Project,
) -> None:
    with pytest.raises(InvalidSprintError) as caught:
        sprint_service.create_sprint(
            session,
            project.id,
            "Sprint 1",
            starts_on=date(2026, 9, 10),
            ends_on=date(2026, 9, 1),
        )
    assert caught.value.code == "sprint.invalid"
    assert "cannot end before it starts" in caught.value.message


def test_a_sprint_may_start_and_end_on_the_same_day(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        "Sprint 1",
        starts_on=date(2026, 9, 10),
        ends_on=date(2026, 9, 10),
    )
    assert sprint.starts_on == sprint.ends_on == date(2026, 9, 10)


def test_updating_the_end_before_the_start_is_refused(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(
        session,
        project.id,
        "Sprint 1",
        starts_on=date(2026, 9, 10),
    )
    with pytest.raises(InvalidSprintError):
        sprint_service.update_sprint(
            session,
            sprint.id,
            ends_on=date(2026, 9, 1),
        )


def test_starting_moves_planned_to_active(session: Session, project: Project) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    started = sprint_service.start_sprint(session, sprint.id)
    assert started.state is SprintState.ACTIVE


def test_a_second_start_in_the_same_project_is_refused(
    session: Session,
    project: Project,
) -> None:
    first = sprint_service.create_sprint(session, project.id, "One")
    second = sprint_service.create_sprint(session, project.id, "Two")
    sprint_service.start_sprint(session, first.id)

    with pytest.raises(SprintAlreadyActiveError) as caught:
        sprint_service.start_sprint(session, second.id)
    assert caught.value.code == "sprint.already_active"


def test_another_project_may_have_its_own_active_sprint(
    session: Session,
    project: Project,
) -> None:
    other = project_service.create_project(session, "SITE", "Site")
    sprint_service.start_sprint(
        session,
        sprint_service.create_sprint(session, project.id, "Keel sprint").id,
    )
    started = sprint_service.start_sprint(
        session,
        sprint_service.create_sprint(session, other.id, "Site sprint").id,
    )
    assert started.state is SprintState.ACTIVE


def test_completing_a_planned_sprint_is_refused(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    with pytest.raises(SprintInvalidTransitionError) as caught:
        sprint_service.complete_sprint(session, sprint.id)
    assert caught.value.code == "sprint.invalid_transition"


def test_starting_an_active_sprint_is_refused(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    sprint_service.start_sprint(session, sprint.id)
    with pytest.raises(SprintInvalidTransitionError):
        sprint_service.start_sprint(session, sprint.id)


def test_completion_carries_unfinished_work_to_the_next_planned_sprint(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Now")
    later = sprint_service.create_sprint(
        session,
        project.id,
        "Next",
        starts_on=date(2026, 10, 1),
    )
    open_id = issue_id(session, project, "Open", sprint_id=current.id)
    done_id = issue_id(session, project, "Done", sprint_id=current.id)
    issue_service.update_issue(session, done_id, status=IssueStatus.DONE)
    sprint_service.start_sprint(session, current.id)

    result = sprint_service.complete_sprint(session, current.id)

    assert result.sprint.state is SprintState.COMPLETED
    assert result.carried_over == 1
    assert result.carried_to_sprint_id == later.id
    assert issue_service.get_issue(session, open_id).sprint_id == later.id
    assert issue_service.get_issue(session, done_id).sprint_id == current.id


def test_completion_returns_work_to_the_backlog_when_nothing_is_planned(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Now")
    open_id = issue_id(session, project, "Open", sprint_id=current.id)
    sprint_service.start_sprint(session, current.id)

    result = sprint_service.complete_sprint(session, current.id)

    assert result.carried_to_sprint_id is None
    assert result.carried_over == 1
    assert issue_service.get_issue(session, open_id).sprint_id is None


def test_the_earliest_planned_sprint_wins_on_carry_over(
    session: Session,
    project: Project,
) -> None:
    current = sprint_service.create_sprint(session, project.id, "Now")
    later = sprint_service.create_sprint(
        session,
        project.id,
        "Later",
        starts_on=date(2026, 11, 1),
    )
    sooner = sprint_service.create_sprint(
        session,
        project.id,
        "Sooner",
        starts_on=date(2026, 10, 1),
    )
    assert later.id != sooner.id
    open_id = issue_id(session, project, "Open", sprint_id=current.id)
    sprint_service.start_sprint(session, current.id)

    result = sprint_service.complete_sprint(session, current.id)
    assert result.carried_to_sprint_id == sooner.id
    assert issue_service.get_issue(session, open_id).sprint_id == sooner.id


def test_an_issue_cannot_join_another_projects_sprint(
    session: Session,
    project: Project,
) -> None:
    other = project_service.create_project(session, "SITE", "Site")
    foreign = sprint_service.create_sprint(session, other.id, "Site sprint")
    local = issue_id(session, project)

    with pytest.raises(SprintProjectMismatchError) as caught:
        issue_service.update_issue(session, local, sprint_id=foreign.id)
    assert caught.value.code == "sprint.project_mismatch"


def test_deleting_a_sprint_unschedules_its_issues(
    session: Session,
    project: Project,
) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    work = issue_id(session, project, sprint_id=sprint.id)
    sprint_service.delete_sprint(session, sprint.id)
    session.expire_all()

    assert issue_service.get_issue(session, work).sprint_id is None


def test_sprint_and_unscheduled_filters(session: Session, project: Project) -> None:
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    scheduled = issue_id(session, project, "In sprint", sprint_id=sprint.id)
    waiting = issue_id(session, project, "Waiting")

    in_sprint = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(sprint_id=sprint.id),
    )
    waiting_list = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(unscheduled=True),
    )

    assert [item.id for item in in_sprint] == [scheduled]
    assert [item.id for item in waiting_list] == [waiting]
