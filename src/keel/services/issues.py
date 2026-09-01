from collections.abc import Sequence
from dataclasses import dataclass

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
)
from keel.domain.hierarchy import IssueRef, check_children, check_parent
from keel.services import projects as project_service

MAX_TITLE_LENGTH = 300
UNSET = object()


@dataclass(frozen=True)
class IssueFilters:
    type: IssueType | None = None
    types: tuple[IssueType, ...] = ()
    status: IssueStatus | None = None
    assignee_id: int | None = None
    parent_id: int | None = None


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
) -> Issue:
    project = project_service.get_project(session, project_id)
    issue = Issue(
        project_id=project.id,
        number=project_service.next_issue_number(session, project),
        type=type,
        title=_clean_title(title),
        description=description.strip(),
        status=status,
        reporter_id=reporter_id,
        assignee_id=assignee_id,
    )
    _assign_parent(session, issue, parent_id)
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
) -> Issue:
    """`parent_id` and `assignee_id` accept None as "clear it", so they use UNSET."""
    issue = get_issue(session, issue_id)

    if type is not None and type is not issue.type:
        check_children(type, [child.type for child in list_children(session, issue.id)])
        issue.type = type
        _assign_parent(session, issue, issue.parent_id)

    if title is not None:
        issue.title = _clean_title(title)
    if description is not None:
        issue.description = description.strip()
    if status is not None:
        issue.status = status
    if parent_id is not UNSET:
        _assign_parent(session, issue, parent_id)  # type: ignore[arg-type]
    if assignee_id is not UNSET:
        issue.assignee_id = assignee_id  # type: ignore[assignment]

    session.flush()
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
    session.delete(issue)
    session.flush()


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
    if filters.assignee_id is not None:
        query = query.where(Issue.assignee_id == filters.assignee_id)
    if filters.parent_id is not None:
        query = query.where(Issue.parent_id == filters.parent_id)
    return query


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise InvalidIssueError("An issue needs a title.")
    return cleaned[:MAX_TITLE_LENGTH]
