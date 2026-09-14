from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project
from keel.domain.enums import (
    INITIAL_STATUS,
    IssueStatus,
    IssueType,
    statuses_in_workflow_order,
)
from keel.domain.errors import (
    InvalidIssueError,
    IssueHasChildrenError,
    NotFoundError,
    SprintProjectMismatchError,
)
from keel.domain.hierarchy import IssueRef, check_children, check_parent
from keel.domain.rollup import EffortNode, Rollup, compute_rollup
from keel.services import projects as project_service

MAX_TITLE_LENGTH = 300
UNSET = object()


@dataclass(frozen=True)
class IssueFilters:
    type: IssueType | None = None
    types: tuple[IssueType, ...] = ()
    status: IssueStatus | None = None
    assignee_id: int | None = None
    unassigned: bool = False
    parent_id: int | None = None
    sprint_id: int | None = None
    unscheduled: bool = False


def issue_key(issue: Issue, project: Project) -> str:
    return f"{project.key}-{issue.number}"


def get_issue(session: Session, issue_id: int) -> Issue:
    issue = session.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError(f"No issue with id {issue_id}.")
    return issue


def get_issue_by_key(session: Session, key: str) -> Issue:
    """Resolves the readable `KEEL-12` form used in web URLs."""
    project_key, _, number = key.rpartition("-")
    if not project_key or not number.isdigit():
        raise NotFoundError(f"{key} is not an issue key.")
    project = project_service.get_project_by_key(session, project_key)
    issue = session.scalars(
        select(Issue).where(
            Issue.project_id == project.id,
            Issue.number == int(number),
        ),
    ).first()
    if issue is None:
        raise NotFoundError(f"No issue {key}.")
    return issue


def list_issues(
    session: Session,
    project_id: int,
    filters: IssueFilters | None = None,
) -> Sequence[Issue]:
    query = select(Issue).where(Issue.project_id == project_id)
    query = _apply_filters(query, filters or IssueFilters())
    return session.scalars(query.order_by(Issue.number)).all()


def list_issues_globally(session: Session) -> Sequence[Issue]:
    """Every issue, for pickers that may cross projects."""
    return session.scalars(
        select(Issue)
        .join(Project, Issue.project_id == Project.id)
        .order_by(Project.key, Issue.number),
    ).all()


def count_by_status(session: Session, project_id: int) -> dict[IssueStatus, int]:
    """Every status appears, including the ones with nothing in them."""
    counts = dict.fromkeys(statuses_in_workflow_order(), 0)
    rows = session.execute(
        select(Issue.status, func.count())
        .where(Issue.project_id == project_id)
        .group_by(Issue.status),
    ).all()
    for status, total in rows:
        counts[status] = total
    return counts


def list_children(session: Session, issue_id: int) -> Sequence[Issue]:
    return session.scalars(
        select(Issue).where(Issue.parent_id == issue_id).order_by(Issue.number),
    ).all()


def create_issue(
    session: Session,
    project_id: int,
    type: IssueType,
    title: str,
    description: str = "",
    status: IssueStatus = INITIAL_STATUS,
    parent_id: int | None = None,
    reporter_id: int | None = None,
    assignee_id: int | None = None,
    due_at: datetime | None = None,
    sprint_id: int | None = None,
    estimate_minutes: int | None = None,
    remaining_minutes: int | None = None,
    series_id: int | None = None,
    occurrence_on: date | None = None,
) -> Issue:
    project = project_service.get_project(session, project_id)
    _check_minutes(estimate_minutes)
    _check_minutes(remaining_minutes)
    if remaining_minutes is None:
        remaining_minutes = estimate_minutes
    issue = Issue(
        project_id=project.id,
        number=project_service.next_issue_number(session, project),
        type=type,
        title=_clean_title(title),
        description=description.strip(),
        status=status,
        reporter_id=reporter_id,
        assignee_id=assignee_id,
        due_at=due_at,
        estimate_minutes=estimate_minutes,
        remaining_minutes=remaining_minutes,
        series_id=series_id,
        occurrence_on=occurrence_on,
    )
    _assign_parent(session, issue, parent_id)
    _assign_sprint(session, issue, sprint_id)
    session.add(issue)
    session.flush()
    return issue


def update_issue(
    session: Session,
    issue_id: int,
    *,
    type: IssueType | None = None,
    title: str | None = None,
    description: str | None = None,
    status: IssueStatus | None = None,
    parent_id: int | None | object = UNSET,
    assignee_id: int | None | object = UNSET,
    due_at: datetime | None | object = UNSET,
    sprint_id: int | None | object = UNSET,
    estimate_minutes: int | None | object = UNSET,
    remaining_minutes: int | None | object = UNSET,
    actor_name: str | None = None,
) -> Issue:
    """Nullable fields accept None as "clear it", so they use UNSET."""
    from keel.services import history as history_service

    issue = get_issue(session, issue_id)
    who = actor_name if actor_name is not None else history_service.current_actor_name()

    if type is not None and type is not issue.type:
        check_children(type, [child.type for child in list_children(session, issue.id)])
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_TYPE,
            from_value=history_service.type_label(issue.type),
            to_value=history_service.type_label(type),
            actor_name=who,
        )
        issue.type = type
        _assign_parent(session, issue, issue.parent_id)

    if title is not None:
        issue.title = _clean_title(title)
    if description is not None:
        issue.description = description.strip()
    if status is not None and status is not issue.status:
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_STATUS,
            from_value=history_service.status_label(issue.status),
            to_value=history_service.status_label(status),
            actor_name=who,
        )
        issue.status = status
    if parent_id is not UNSET and parent_id != issue.parent_id:
        old_parent = history_service.parent_label(session, issue.parent_id)
        new_parent = history_service.parent_label(session, parent_id)  # type: ignore[arg-type]
        _assign_parent(session, issue, parent_id)  # type: ignore[arg-type]
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_PARENT,
            from_value=old_parent,
            to_value=new_parent,
            actor_name=who,
        )
    if assignee_id is not UNSET and assignee_id != issue.assignee_id:
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_ASSIGNEE,
            from_value=history_service.assignee_label(session, issue.assignee_id),
            to_value=history_service.assignee_label(session, assignee_id),  # type: ignore[arg-type]
            actor_name=who,
        )
        issue.assignee_id = assignee_id  # type: ignore[assignment]
    if due_at is not UNSET and due_at != issue.due_at:
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_DUE,
            from_value=history_service.due_label(issue.due_at),
            to_value=history_service.due_label(due_at),  # type: ignore[arg-type]
            actor_name=who,
        )
        issue.due_at = due_at  # type: ignore[assignment]
    if sprint_id is not UNSET and sprint_id != issue.sprint_id:
        old_sprint = history_service.sprint_label(session, issue.sprint_id)
        new_sprint = history_service.sprint_label(session, sprint_id)  # type: ignore[arg-type]
        _assign_sprint(session, issue, sprint_id)  # type: ignore[arg-type]
        history_service.record(
            session,
            issue.id,
            field=history_service.FIELD_SPRINT,
            from_value=old_sprint,
            to_value=new_sprint,
            actor_name=who,
        )
    if estimate_minutes is not UNSET:
        _check_minutes(estimate_minutes)  # type: ignore[arg-type]
        if estimate_minutes != issue.estimate_minutes:
            history_service.record(
                session,
                issue.id,
                field=history_service.FIELD_ESTIMATE,
                from_value=history_service.effort_label(issue.estimate_minutes),
                to_value=history_service.effort_label(estimate_minutes),  # type: ignore[arg-type]
                actor_name=who,
            )
            issue.estimate_minutes = estimate_minutes  # type: ignore[assignment]
    if remaining_minutes is not UNSET:
        _check_minutes(remaining_minutes)  # type: ignore[arg-type]
        if remaining_minutes != issue.remaining_minutes:
            history_service.record(
                session,
                issue.id,
                field=history_service.FIELD_REMAINING,
                from_value=history_service.effort_label(issue.remaining_minutes),
                to_value=history_service.effort_label(remaining_minutes),  # type: ignore[arg-type]
                actor_name=who,
            )
            issue.remaining_minutes = remaining_minutes  # type: ignore[assignment]

    session.flush()
    if status is not None:
        from keel.services import series as series_service

        series_service.on_occurrence_closed(session, issue)
    return issue


def delete_issue(session: Session, issue_id: int) -> None:
    issue = get_issue(session, issue_id)
    children = list_children(session, issue.id)
    if children:
        raise IssueHasChildrenError(
            "Move or delete this issue's children first.",
            issue_id=issue.id,
            children=len(children),
        )
    series_id = issue.series_id
    occurrence_on = issue.occurrence_on
    session.delete(issue)
    session.flush()
    if series_id is not None and occurrence_on is not None:
        from keel.services import series as series_service

        series_service.after_issue_deleted(session, series_id, occurrence_on)


def issue_rollup(session: Session, issue_id: int) -> Rollup:
    """Subtree totals for one issue, loaded with a recursive parent walk."""
    issue = get_issue(session, issue_id)
    nodes = [
        EffortNode(
            id=item.id,
            estimate_minutes=item.estimate_minutes,
            remaining_minutes=item.remaining_minutes,
            status=item.status,
        )
        for item in _load_subtree(session, issue.id)
    ]
    return compute_rollup(issue.id, nodes)


def ancestor_ids(session: Session, issue_id: int) -> list[int]:
    """Walks upward from an issue, stopping if the data already holds a loop."""
    seen: list[int] = []
    current = session.get(Issue, issue_id)
    while current is not None and current.parent_id is not None:
        if current.parent_id in seen:
            break
        seen.append(current.parent_id)
        current = session.get(Issue, current.parent_id)
    return seen


def _assign_parent(session: Session, issue: Issue, parent_id: int | None) -> None:
    parent = None if parent_id is None else get_issue(session, parent_id)
    check_parent(
        IssueRef(id=issue.id, type=issue.type, project_id=issue.project_id),
        None
        if parent is None
        else IssueRef(id=parent.id, type=parent.type, project_id=parent.project_id),
        () if parent is None else ancestor_ids(session, parent.id),
    )
    issue.parent_id = parent_id


def _assign_sprint(session: Session, issue: Issue, sprint_id: int | None) -> None:
    if sprint_id is None:
        issue.sprint_id = None
        return
    from keel.services.sprints import get_sprint

    sprint = get_sprint(session, sprint_id)
    if sprint.project_id != issue.project_id:
        raise SprintProjectMismatchError(
            "An issue can only be scheduled in a sprint of the same project.",
            issue_id=issue.id,
            sprint_id=sprint.id,
        )
    issue.sprint_id = sprint_id


def _apply_filters(
    query: Select[tuple[Issue]],
    filters: IssueFilters,
) -> Select[tuple[Issue]]:
    if filters.types:
        chosen = set(filters.types)
        if chosen != set(IssueType):
            query = query.where(Issue.type.in_(filters.types))
    elif filters.type is not None:
        query = query.where(Issue.type == filters.type)
    if filters.status is not None:
        query = query.where(Issue.status == filters.status)
    if filters.unassigned:
        query = query.where(Issue.assignee_id.is_(None))
    elif filters.assignee_id is not None:
        query = query.where(Issue.assignee_id == filters.assignee_id)
    if filters.parent_id is not None:
        query = query.where(Issue.parent_id == filters.parent_id)
    if filters.unscheduled:
        query = query.where(Issue.sprint_id.is_(None))
    elif filters.sprint_id is not None:
        query = query.where(Issue.sprint_id == filters.sprint_id)
    return query


def _load_subtree(session: Session, root_id: int) -> Sequence[Issue]:
    tree = (
        select(Issue.id)
        .where(Issue.id == root_id)
        .cte(
            name="issue_tree",
            recursive=True,
        )
    )
    tree = tree.union_all(select(Issue.id).where(Issue.parent_id == tree.c.id))
    return session.scalars(
        select(Issue).where(Issue.id.in_(select(tree.c.id))).order_by(Issue.id),
    ).all()


def parse_due_at(raw: str) -> datetime | None:
    """Read a datetime-local or ISO string. Blank means no due date."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise InvalidIssueError("Due date could not be read.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise InvalidIssueError("An issue needs a title.")
    return cleaned[:MAX_TITLE_LENGTH]


def _check_minutes(value: int | None) -> None:
    if value is not None and value < 0:
        raise InvalidIssueError("Effort cannot be negative.")
