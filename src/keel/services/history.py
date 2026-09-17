from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, IssueHistory, Project, Sprint, User
from keel.domain.duration import format_minutes
from keel.domain.enums import IssuePriority, IssueStatus, IssueType, label
from keel.services.identity import acting_display_name

SYSTEM_ACTOR = "Keel"

FIELD_STATUS = "status"
FIELD_ASSIGNEE = "assignee"
FIELD_SPRINT = "sprint"
FIELD_ESTIMATE = "estimate"
FIELD_REMAINING = "remaining"
FIELD_DUE = "due date"
FIELD_PARENT = "parent"
FIELD_TYPE = "type"
FIELD_PRIORITY = "priority"
FIELD_TITLE = "title"
FIELD_DESCRIPTION = "description"
FIELD_LABELS = "labels"

UNASSIGNED = "Unassigned"
UNSCHEDULED = "Unscheduled"
NO_PARENT = "No parent"
NONE = "none"


def current_actor_name() -> str:
    return acting_display_name() or SYSTEM_ACTOR


def list_history(session: Session, issue_id: int) -> Sequence[IssueHistory]:
    from keel.services import issues as issue_service

    issue_service.get_issue(session, issue_id)
    return session.scalars(
        select(IssueHistory)
        .where(IssueHistory.issue_id == issue_id)
        .order_by(IssueHistory.created_at, IssueHistory.id),
    ).all()


def record(
    session: Session,
    issue_id: int,
    *,
    field: str,
    from_value: str,
    to_value: str,
    actor_name: str | None = None,
) -> IssueHistory | None:
    """Append one line when the snapshotted labels differ."""
    if from_value == to_value:
        return None
    event = IssueHistory(
        issue_id=issue_id,
        actor_name=actor_name if actor_name is not None else current_actor_name(),
        field=field,
        from_value=from_value,
        to_value=to_value,
    )
    session.add(event)
    session.flush()
    return event


def status_label(value: IssueStatus) -> str:
    return label(value)


def type_label(value: IssueType) -> str:
    return label(value)


def priority_label(value: IssuePriority) -> str:
    return label(value)


def assignee_label(session: Session, user_id: int | None) -> str:
    if user_id is None:
        return UNASSIGNED
    person = session.get(User, user_id)
    if person is None:
        return UNASSIGNED
    return person.display_name


def sprint_label(session: Session, sprint_id: int | None) -> str:
    if sprint_id is None:
        return UNSCHEDULED
    sprint = session.get(Sprint, sprint_id)
    if sprint is None:
        return UNSCHEDULED
    return sprint.name


def parent_label(session: Session, parent_id: int | None) -> str:
    if parent_id is None:
        return NO_PARENT
    parent = session.get(Issue, parent_id)
    if parent is None:
        return NO_PARENT
    project = session.get(Project, parent.project_id)
    if project is None:
        return NO_PARENT
    return f"{project.key}-{parent.number}"


def effort_label(minutes: int | None) -> str:
    if minutes is None:
        return NONE
    return format_minutes(minutes)


def due_label(value: datetime | None) -> str:
    if value is None:
        return NONE
    return value.strftime("%Y-%m-%d %H:%M UTC")


def text_label(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return NONE
    return cleaned


def labels_label(names: Sequence[str]) -> str:
    cleaned = [name for name in names if name]
    if not cleaned:
        return NONE
    return ", ".join(sorted(cleaned))
