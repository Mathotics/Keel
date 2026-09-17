"""Personal inbox at `/`: the acting user's work across projects."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project, Sprint
from keel.domain.enums import (
    CLOSED_STATUSES,
    IssueStatus,
    SprintState,
    statuses_in_workflow_order,
)
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service

_STATUS_ORDER = {
    status: index for index, status in enumerate(statuses_in_workflow_order())
}


@dataclass(frozen=True)
class HomeRow:
    issue: Issue
    project: Project
    key: str
    unresolved_blockers: int
    sprint_name: str | None


@dataclass(frozen=True)
class HomeInbox:
    assigned: tuple[HomeRow, ...] = ()
    due: tuple[HomeRow, ...] = ()
    starting: tuple[HomeRow, ...] = ()
    blocked: tuple[HomeRow, ...] = ()
    active_sprint: tuple[HomeRow, ...] = ()
    waiting: tuple[HomeRow, ...] = ()

    @property
    def empty(self) -> bool:
        return not (
            self.assigned
            or self.due
            or self.starting
            or self.blocked
            or self.active_sprint
            or self.waiting
        )


def personal_inbox(
    session: Session,
    assignee_id: int,
    *,
    today: date | None = None,
) -> HomeInbox:
    """Issues assigned to one user, partitioned into overlapping home sections."""
    day = today or datetime.now(UTC).date()
    found = session.execute(
        select(Issue, Project, Sprint)
        .join(Project, Issue.project_id == Project.id)
        .outerjoin(Sprint, Issue.sprint_id == Sprint.id)
        .where(Issue.assignee_id == assignee_id),
    ).all()
    counts = dependency_service.unresolved_blocker_counts(
        session,
        [issue.id for issue, _project, _sprint in found],
    )
    packed: list[tuple[HomeRow, Sprint | None]] = []
    for issue, project, sprint in found:
        packed.append(
            (
                HomeRow(
                    issue=issue,
                    project=project,
                    key=issue_service.issue_key(issue, project),
                    unresolved_blockers=counts.get(issue.id, 0),
                    sprint_name=sprint.name if sprint is not None else None,
                ),
                sprint,
            ),
        )
    unfinished = [
        item for item, _sprint in packed if item.issue.status not in CLOSED_STATUSES
    ]
    return HomeInbox(
        assigned=_sorted_by_key(unfinished),
        due=_sorted_by_due(
            [
                item
                for item in unfinished
                if item.issue.due_at is not None
                and _calendar_day(item.issue.due_at) <= day
            ],
        ),
        starting=_sorted_by_start(
            [
                item
                for item in unfinished
                if item.issue.start_at is not None
                and _calendar_day(item.issue.start_at) <= day
            ],
        ),
        blocked=_sorted_by_key(
            [
                item
                for item in unfinished
                if item.issue.status is IssueStatus.BLOCKED
                or item.unresolved_blockers > 0
            ],
        ),
        active_sprint=_sorted_by_sprint(
            [
                item
                for item, sprint in packed
                if sprint is not None and sprint.state is SprintState.ACTIVE
            ],
        ),
        waiting=_sorted_by_occurrence(
            [
                item
                for item in unfinished
                if item.issue.series_id is not None
                and item.issue.occurrence_on is not None
                and item.issue.occurrence_on <= day
            ],
        ),
    )


def _calendar_day(value: datetime) -> date:
    if value.tzinfo is not None:
        return value.astimezone(UTC).date()
    return value.date()


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _sorted_by_key(items: Sequence[HomeRow]) -> tuple[HomeRow, ...]:
    return tuple(sorted(items, key=lambda item: (item.project.key, item.issue.number)))


def _sorted_by_due(items: Sequence[HomeRow]) -> tuple[HomeRow, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                _as_naive_utc(item.issue.due_at) if item.issue.due_at else datetime.min,
                item.project.key,
                item.issue.number,
            ),
        ),
    )


def _sorted_by_start(items: Sequence[HomeRow]) -> tuple[HomeRow, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                _as_naive_utc(item.issue.start_at)
                if item.issue.start_at
                else datetime.min,
                item.project.key,
                item.issue.number,
            ),
        ),
    )


def _sorted_by_sprint(items: Sequence[HomeRow]) -> tuple[HomeRow, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.project.key,
                _STATUS_ORDER[item.issue.status],
                item.issue.number,
            ),
        ),
    )


def _sorted_by_occurrence(items: Sequence[HomeRow]) -> tuple[HomeRow, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.issue.occurrence_on or date.min,
                item.project.key,
                item.issue.number,
            ),
        ),
    )
