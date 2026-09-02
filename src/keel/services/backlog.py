from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue
from keel.domain.enums import TERMINAL_STATUS
from keel.services import projects as project_service


def project_backlog(session: Session, project_id: int) -> Sequence[Issue]:
    """Unscheduled issues that are not Done, oldest first."""
    project_service.get_project(session, project_id)
    return session.scalars(
        select(Issue)
        .where(
            Issue.project_id == project_id,
            Issue.sprint_id.is_(None),
            Issue.status != TERMINAL_STATUS,
        )
        .order_by(Issue.created_at, Issue.id),
    ).all()
