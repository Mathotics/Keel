"""Suggestions for issue and label fields that grow without a fixed set."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, cast, literal, or_, select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Label, Project
from keel.domain.errors import InvalidIssueError, NotFoundError
from keel.domain.labels import normalize_label_name
from keel.services import issues as issue_service
from keel.services import projects as project_service

LIMIT = 10
UNLABELED = "unlabeled"
SEPARATOR = " \u2014 "
PARENT_MESSAGE = "Choose a parent issue."
LINK_MESSAGE = "Choose an issue to link."
LABEL_MESSAGE = "Choose a label from the list."


@dataclass(frozen=True)
class IssueSuggestion:
    id: int
    key: str
    title: str


def issue_display(key: str, title: str) -> str:
    return f"{key}{SEPARATOR}{title}"


def parent_field_value(
    session: Session,
    parent_id: int | None,
    project: Project,
) -> str:
    if parent_id is None:
        return ""
    parent = issue_service.get_issue(session, parent_id)
    return issue_display(issue_service.issue_key(parent, project), parent.title)


def suggest_issues(
    session: Session,
    query: str,
    *,
    project_id: int | None = None,
    exclude_id: int | None = None,
) -> list[IssueSuggestion]:
    needle = query.strip()
    if not needle:
        return []
    pattern = _like_pattern(needle)
    key_expr = Project.key.concat(literal("-")).concat(cast(Issue.number, String))
    stmt = (
        select(Issue, Project)
        .join(Project, Issue.project_id == Project.id)
        .where(
            or_(
                Issue.title.ilike(pattern, escape="\\"),
                key_expr.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Project.key, Issue.number)
        .limit(LIMIT)
    )
    if project_id is not None:
        stmt = stmt.where(Issue.project_id == project_id)
    if exclude_id is not None:
        stmt = stmt.where(Issue.id != exclude_id)
    return [
        IssueSuggestion(
            id=issue.id,
            key=issue_service.issue_key(issue, project),
            title=issue.title,
        )
        for issue, project in session.execute(stmt).all()
    ]


def suggest_labels(session: Session, query: str) -> list[str]:
    needle = query.strip().lower()
    names = session.scalars(select(Label.name).order_by(Label.name)).all()
    results: list[str] = []
    if not needle or UNLABELED.startswith(needle):
        results.append(UNLABELED)
    if needle:
        for name in names:
            if needle in name and name not in results:
                results.append(name)
            if len(results) >= LIMIT:
                break
    return results[:LIMIT]


def resolve_posted_issue(
    session: Session,
    raw_id: str,
    raw_query: str,
    *,
    project_id: int | None,
    message: str,
) -> int | None:
    """An explicit id wins. Otherwise an exact key, or `KEY — title`."""
    chosen = raw_id.strip()
    if chosen.isdigit():
        return int(chosen)
    text = raw_query.strip()
    if not text:
        return None
    key = text.split(SEPARATOR, 1)[0].strip()
    try:
        issue = issue_service.get_issue_by_key(session, key)
    except NotFoundError:
        raise InvalidIssueError(message) from None
    if project_id is not None and issue.project_id != project_id:
        raise InvalidIssueError(message)
    return issue.id


def interpret_board_label(
    session: Session,
    raw: str | None,
) -> tuple[str | None, bool, str | None]:
    """Name, unlabeled flag, and a message when the text is not a real label."""
    if raw is None or not raw.strip():
        return None, False, None
    cleaned = raw.strip()
    if cleaned == UNLABELED:
        return None, True, None
    try:
        name = normalize_label_name(cleaned)
    except InvalidIssueError as exc:
        return None, False, exc.message
    known = session.scalar(select(Label.id).where(Label.name == name))
    if known is None:
        return None, False, LABEL_MESSAGE
    return name, False, None


def project_id_for_key(session: Session, key: str | None) -> int | None:
    if key is None or not key.strip():
        return None
    try:
        return project_service.get_project_by_key(session, key).id
    except NotFoundError:
        return None


def _like_pattern(needle: str) -> str:
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
