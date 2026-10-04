"""Suggestions for issue and label fields that grow without a fixed set."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Label, Project, User
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
UNASSIGNED = "unassigned"
UNASSIGNED_LABEL = "Unassigned"
USER_MESSAGE = "Choose a person from the list."


@dataclass(frozen=True)
class IssueSuggestion:
    id: int
    key: str
    title: str


@dataclass(frozen=True)
class UserSuggestion:
    id: int | None
    label: str


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


def user_field_value(session: Session, user_id: int | None) -> str:
    if user_id is None:
        return ""
    user = session.get(User, user_id)
    if user is None:
        return ""
    return user.display_name


def suggest_users(session: Session, query: str) -> list[UserSuggestion]:
    """People by display name or username, plus Unassigned while it matches."""
    needle = query.strip().lower()
    results: list[UserSuggestion] = []
    if not needle or UNASSIGNED.startswith(needle):
        results.append(UserSuggestion(id=None, label=UNASSIGNED_LABEL))
    if needle:
        pattern = _like_pattern(needle)
        people = session.scalars(
            select(User)
            .where(
                or_(
                    User.display_name.ilike(pattern, escape="\\"),
                    User.username.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(User.display_name, User.id)
            .limit(LIMIT),
        )
        for user in people:
            if user.display_name.casefold() == UNASSIGNED:
                continue
            results.append(UserSuggestion(id=user.id, label=user.display_name))
            if len(results) >= LIMIT:
                break
    return results[:LIMIT]


def resolve_posted_user(session: Session, raw_id: str, raw_query: str) -> int | None:
    """An explicit id wins. Otherwise Unassigned, or an exact person."""
    chosen = raw_id.strip()
    if chosen.isdigit():
        return int(chosen)
    text = raw_query.strip()
    if not text or _is_unassigned_text(text):
        return None
    user = _user_named(session, text)
    if user is None:
        raise InvalidIssueError(USER_MESSAGE)
    return user.id


def interpret_board_assignee(
    session: Session,
    raw: str | None,
) -> tuple[int | None, bool, str, str | None]:
    """Id, unassigned flag, the text to show, and a message when it is not a person.

    Empty means every assignee. Unassigned means no assignee. A number is a
    user id. Anything else is a display name or username.
    """
    if raw is None or not raw.strip():
        return None, False, "", None
    cleaned = raw.strip()
    if _is_unassigned_text(cleaned):
        return None, True, UNASSIGNED_LABEL, None
    if cleaned.isdigit():
        user = session.get(User, int(cleaned))
        if user is None:
            return None, False, cleaned, USER_MESSAGE
        return user.id, False, user.display_name, None
    user = _user_named(session, cleaned)
    if user is None:
        return None, False, cleaned, USER_MESSAGE
    return user.id, False, user.display_name, None


def project_id_for_key(session: Session, key: str | None) -> int | None:
    if key is None or not key.strip():
        return None
    try:
        return project_service.get_project_by_key(session, key).id
    except NotFoundError:
        return None


def _is_unassigned_text(text: str) -> bool:
    return text.casefold() == UNASSIGNED


def _user_named(session: Session, text: str) -> User | None:
    exact = session.scalar(select(User).where(User.display_name == text))
    if exact is not None and exact.display_name.casefold() != UNASSIGNED:
        return exact
    lowered = text.casefold()
    by_display = [
        user
        for user in session.scalars(
            select(User).where(func.lower(User.display_name) == lowered),
        )
        if user.display_name.casefold() != UNASSIGNED
    ]
    if len(by_display) == 1:
        return by_display[0]
    if len(by_display) > 1:
        return None
    by_username = list(
        session.scalars(select(User).where(func.lower(User.username) == lowered)),
    )
    if len(by_username) == 1:
        return by_username[0]
    return None


def _like_pattern(needle: str) -> str:
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
