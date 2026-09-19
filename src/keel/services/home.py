"""Personal inbox at `/`: the acting user's work across projects."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, IssueHistory, Project, Sprint
from keel.domain.enums import (
    CLOSED_STATUSES,
    IssueStatus,
    SprintState,
    statuses_in_workflow_order,
)
from keel.services import dependencies as dependency_service
from keel.services import history as history_service
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
    completed_at: datetime | None = None


@dataclass(frozen=True)
class HomeInbox:
    assigned: tuple[HomeRow, ...] = ()
    due: tuple[HomeRow, ...] = ()
    starting: tuple[HomeRow, ...] = ()
    blocked: tuple[HomeRow, ...] = ()
    active_sprint: tuple[HomeRow, ...] = ()
    waiting: tuple[HomeRow, ...] = ()
    completed: tuple[HomeRow, ...] = ()

    @property
    def empty(self) -> bool:
        return not (
            self.assigned
            or self.due
            or self.starting
            or self.blocked
            or self.active_sprint
            or self.waiting
            or self.completed
        )


def personal_inbox(
    session: Session,
    assignee_id: int,
    *,
    today: date | None = None,
) -> HomeInbox:
    """Issues assigned to one user, partitioned into overlapping home sections."""
    day = today or date.today()
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
    times = _completion_times(session, [item.issue for item, _sprint in packed])
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
        completed=_sorted_by_completed(
            [
                replace(item, completed_at=times[item.issue.id])
                for item, _sprint in packed
                if item.issue.id in times and _calendar_day(times[item.issue.id]) == day
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


def _sorted_by_completed(items: Sequence[HomeRow]) -> tuple[HomeRow, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (
                datetime.max
                - (
                    _as_naive_utc(item.completed_at)
                    if item.completed_at
                    else datetime.min
                ),
                item.project.key,
                item.issue.number,
            ),
        ),
    )


def _completion_times(session: Session, issues: Sequence[Issue]) -> dict[int, datetime]:
    """Latest move to Done, or created_at when an issue was born Done."""
    done = [issue for issue in issues if issue.status is IssueStatus.DONE]
    if not done:
        return {}
    ids = [issue.id for issue in done]
    rows = session.scalars(
        select(IssueHistory)
        .where(
            IssueHistory.issue_id.in_(ids),
            IssueHistory.field == history_service.FIELD_STATUS,
        )
        .order_by(IssueHistory.created_at, IssueHistory.id),
    ).all()
    latest: dict[int, IssueHistory] = {}
    for row in rows:
        latest[row.issue_id] = row
    done_label = history_service.status_label(IssueStatus.DONE)
    times: dict[int, datetime] = {}
    for issue in done:
        event = latest.get(issue.id)
        if event is None:
            times[issue.id] = issue.created_at
        elif event.to_value == done_label:
            times[issue.id] = event.created_at
    return times
