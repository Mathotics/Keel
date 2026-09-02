from sqlalchemy.orm import Session

from keel.domain.enums import IssueStatus, IssueType
from keel.services import backlog as backlog_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service


def test_the_backlog_is_unscheduled_unfinished_work_oldest_first(
    session: Session,
) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    first = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="First",
    )
    second = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Second",
    )
    done = issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Done already",
    )
    issue_service.update_issue(session, done.id, status=IssueStatus.DONE)
    sprint = sprint_service.create_sprint(session, project.id, "Sprint 1")
    issue_service.update_issue(session, second.id, sprint_id=sprint.id)

    backlog = backlog_service.project_backlog(session, project.id)

    assert [issue.id for issue in backlog] == [first.id]
