from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from keel.db.models import Issue, Project
from keel.domain.enums import IssueStatus, IssueType, statuses_in_workflow_order
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.issues import IssueFilters


@dataclass(frozen=True)
class BoardCard:
    issue: Issue
    key: str
    assignee_name: str | None


@dataclass(frozen=True)
class BoardColumn:
    status: IssueStatus
    cards: tuple[BoardCard, ...]


@dataclass(frozen=True)
class Board:
    project: Project
    columns: tuple[BoardColumn, ...]


def project_board(
    session: Session,
    project_id: int,
    types: Sequence[IssueType] = (),
) -> Board:
    """Group a project's issues by status in workflow order.

    The type filter is applied in the query so hidden cards are never loaded.
    Empty `types` means every type, matching the board's default.
    """
    project = project_service.get_project(session, project_id)
    found = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(types=tuple(types)),
    )
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    grouped: dict[IssueStatus, list[BoardCard]] = {
        status: [] for status in statuses_in_workflow_order()
    }
    for issue in found:
        assignee = names.get(issue.assignee_id) if issue.assignee_id else None
        grouped[issue.status].append(
            BoardCard(
                issue=issue,
                key=issue_service.issue_key(issue, project),
                assignee_name=assignee,
            ),
        )
    return Board(
        project=project,
        columns=tuple(
            BoardColumn(status=status, cards=tuple(grouped[status]))
            for status in statuses_in_workflow_order()
        ),
    )
