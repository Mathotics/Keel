from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue
from keel.domain.enums import CLOSED_STATUSES
from keel.services import dependencies as dependency_service
from keel.services import projects as project_service


@dataclass(frozen=True)
class BacklogItem:
    issue: Issue
    unresolved_blockers: int


def project_backlog(session: Session, project_id: int) -> Sequence[BacklogItem]:
    """Unscheduled issues that are not closed, oldest first."""
    project_service.get_project(session, project_id)
    issues = session.scalars(
        select(Issue)
        .where(
            Issue.project_id == project_id,
            Issue.sprint_id.is_(None),
            Issue.status.notin_(CLOSED_STATUSES),
        )
        .order_by(Issue.created_at, Issue.id),
    ).all()
    counts = dependency_service.unresolved_blocker_counts(
        session,
        [issue.id for issue in issues],
    )
    return tuple(
        BacklogItem(issue=issue, unresolved_blockers=counts.get(issue.id, 0))
        for issue in issues
    )
