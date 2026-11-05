"""Lookup from the top-bar find field: exact jumps, then a short list per kind."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, String, cast, func, literal, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from keel.db.models import Comment, Issue, Project, Sprint, User
from keel.domain.enums import IssueType
from keel.domain.errors import NotFoundError
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services.projects import KEY_PATTERN

PER_KIND = 10
SNIPPET_RADIUS = 40


@dataclass(frozen=True)
class FindJump:
    url: str
    target: str
    issue_id: int | None = None
    project_id: int | None = None
    project_key: str | None = None
    sprint_id: int | None = None
    key: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class IssueHit:
    id: int
    key: str
    title: str
    type: IssueType
    project_key: str
    snippet: str | None


@dataclass(frozen=True)
class ProjectHit:
    id: int
    key: str
    name: str
    snippet: str | None


@dataclass(frozen=True)
class SprintHit:
    id: int
    name: str
    project_id: int
    project_key: str
    snippet: str | None


@dataclass(frozen=True)
class UserHit:
    display_name: str


@dataclass(frozen=True)
class FindResults:
    query: str
    issues: Sequence[IssueHit]
    issues_more: bool
    projects: Sequence[ProjectHit]
    projects_more: bool
    sprints: Sequence[SprintHit]
    sprints_more: bool
    users: Sequence[UserHit]
    users_more: bool

    @property
    def empty(self) -> bool:
        return not (self.issues or self.projects or self.sprints or self.users)


def find(
    session: Session,
    query: str,
    project_id: int | None = None,
) -> FindJump | FindResults:
    needle = query.strip()
    if not needle:
        return FindResults(
            query=needle,
            issues=(),
            issues_more=False,
            projects=(),
            projects_more=False,
            sprints=(),
            sprints_more=False,
            users=(),
            users_more=False,
        )
    jump = _exact_jump(session, needle, project_id)
    if jump is not None:
        return jump
    return _list_matches(session, needle, project_id)


def lookup_jump(
    session: Session,
    query: str,
    project_id: int | None = None,
) -> FindJump | None:
    """An exact key or unique name, when the find field should leave the list."""
    return _exact_jump(session, query.strip(), project_id)


def _exact_jump(
    session: Session,
    needle: str,
    project_id: int | None,
) -> FindJump | None:
    try:
        issue = issue_service.get_issue_by_key(session, needle)
    except NotFoundError:
        issue = None
    if issue is not None:
        project = project_service.get_project(session, issue.project_id)
        key = issue_service.issue_key(issue, project)
        return FindJump(
            url=f"/issues/{key}",
            target="issue",
            issue_id=issue.id,
            project_id=project.id,
            project_key=project.key,
            key=key,
        )
    if KEY_PATTERN.fullmatch(needle.upper()):
        try:
            named = project_service.get_project_by_key(session, needle)
        except NotFoundError:
            named = None
        if named is not None:
            return FindJump(
                url=f"/projects/{named.key}",
                target="project",
                project_id=named.id,
                project_key=named.key,
                key=named.key,
            )
    users = session.scalars(
        select(User).where(func.lower(User.display_name) == needle.lower()),
    ).all()
    if len(users) == 1:
        return FindJump(
            url="/users",
            target="user",
            display_name=users[0].display_name,
        )
    sprints = _sprints_named(session, needle, project_id)
    if len(sprints) == 1:
        sprint = sprints[0]
        project = project_service.get_project(session, sprint.project_id)
        return FindJump(
            url=f"/projects/{project.key}/sprints/{sprint.id}",
            target="sprint",
            project_id=project.id,
            project_key=project.key,
            sprint_id=sprint.id,
        )
    return None


def _sprints_named(
    session: Session,
    needle: str,
    project_id: int | None,
) -> Sequence[Sprint]:
    query = select(Sprint).where(func.lower(Sprint.name) == needle.lower())
    if project_id is not None:
        query = query.where(Sprint.project_id == project_id)
    return session.scalars(query.order_by(Sprint.id)).all()


def match_totals(
    session: Session,
    needle: str,
    project_id: int | None,
) -> tuple[int, int, int, int]:
    """How many issues, projects, sprints, and users match, in that order."""
    pattern = _like_pattern(needle)
    return (
        _count(session, _issue_stmt(pattern, project_id)),
        _count(session, _project_stmt(pattern)),
        _count(session, _sprint_stmt(pattern, project_id)),
        _count(session, _user_stmt(pattern)),
    )


def load_issue_hits(
    session: Session,
    needle: str,
    project_id: int | None,
    *,
    limit: int,
    offset: int,
) -> list[IssueHit]:
    pattern = _like_pattern(needle)
    rows = session.execute(
        _issue_stmt(pattern, project_id)
        .order_by(Project.key, Issue.number)
        .offset(offset)
        .limit(limit),
    ).all()
    hits = []
    for issue, project in rows:
        hits.append(
            IssueHit(
                id=issue.id,
                key=issue_service.issue_key(issue, project),
                title=issue.title,
                type=issue.type,
                project_key=project.key,
                snippet=_issue_snippet(session, issue, project, needle),
            ),
        )
    return hits


def load_project_hits(
    session: Session,
    needle: str,
    *,
    limit: int,
    offset: int,
) -> list[ProjectHit]:
    rows = session.scalars(
        _project_stmt(_like_pattern(needle))
        .order_by(Project.key)
        .offset(offset)
        .limit(limit),
    ).all()
    hits = []
    for project in rows:
        snippet = None
        if not _contains(project.key, needle) and not _contains(project.name, needle):
            snippet = _snippet(project.description, needle)
        hits.append(
            ProjectHit(
                id=project.id, key=project.key, name=project.name, snippet=snippet
            ),
        )
    return hits


def load_sprint_hits(
    session: Session,
    needle: str,
    project_id: int | None,
    *,
    limit: int,
    offset: int,
) -> list[SprintHit]:
    rows = session.execute(
        _sprint_stmt(_like_pattern(needle), project_id)
        .order_by(Project.key, Sprint.id)
        .offset(offset)
        .limit(limit),
    ).all()
    hits = []
    for sprint, project in rows:
        snippet = None
        if not _contains(sprint.name, needle):
            snippet = _snippet(sprint.goal, needle)
        hits.append(
            SprintHit(
                id=sprint.id,
                name=sprint.name,
                project_id=project.id,
                project_key=project.key,
                snippet=snippet,
            ),
        )
    return hits


def load_user_hits(
    session: Session,
    needle: str,
    *,
    limit: int,
    offset: int,
) -> list[UserHit]:
    rows = session.scalars(
        _user_stmt(_like_pattern(needle))
        .order_by(User.display_name)
        .offset(offset)
        .limit(limit),
    ).all()
    return [UserHit(display_name=user.display_name) for user in rows]


def _list_matches(
    session: Session,
    needle: str,
    project_id: int | None,
) -> FindResults:
    issues = load_issue_hits(
        session,
        needle,
        project_id,
        limit=PER_KIND + 1,
        offset=0,
    )
    projects = load_project_hits(session, needle, limit=PER_KIND + 1, offset=0)
    sprints = load_sprint_hits(
        session,
        needle,
        project_id,
        limit=PER_KIND + 1,
        offset=0,
    )
    users = load_user_hits(session, needle, limit=PER_KIND + 1, offset=0)
    return FindResults(
        query=needle,
        issues=issues[:PER_KIND],
        issues_more=len(issues) > PER_KIND,
        projects=projects[:PER_KIND],
        projects_more=len(projects) > PER_KIND,
        sprints=sprints[:PER_KIND],
        sprints_more=len(sprints) > PER_KIND,
        users=users[:PER_KIND],
        users_more=len(users) > PER_KIND,
    )


def _count(session: Session, stmt: Select[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _like_pattern(needle: str) -> str:
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _issue_key_expr() -> ColumnElement[str]:
    return Project.key.concat(literal("-")).concat(cast(Issue.number, String))


def _issue_stmt(pattern: str, project_id: int | None) -> Select[tuple[Issue, Project]]:
    comment_ids = select(Comment.issue_id).where(
        Comment.body.ilike(pattern, escape="\\"),
    )
    stmt = (
        select(Issue, Project)
        .join(Project, Issue.project_id == Project.id)
        .where(
            or_(
                Issue.title.ilike(pattern, escape="\\"),
                Issue.description.ilike(pattern, escape="\\"),
                Issue.definition_of_done.ilike(pattern, escape="\\"),
                Issue.location.ilike(pattern, escape="\\"),
                _issue_key_expr().ilike(pattern, escape="\\"),
                Issue.id.in_(comment_ids),
            ),
        )
    )
    if project_id is not None:
        stmt = stmt.where(Issue.project_id == project_id)
    return stmt


def _issue_snippet(
    session: Session,
    issue: Issue,
    project: Project,
    needle: str,
) -> str | None:
    key = issue_service.issue_key(issue, project)
    if _contains(key, needle) or _contains(issue.title, needle):
        return None
    snippet = _snippet(issue.description, needle)
    if snippet is not None:
        return snippet
    snippet = _snippet(issue.definition_of_done, needle)
    if snippet is not None:
        return snippet
    snippet = _snippet(issue.location, needle)
    if snippet is not None:
        return snippet
    comments = session.scalars(
        select(Comment).where(Comment.issue_id == issue.id).order_by(Comment.id),
    )
    for comment in comments:
        snippet = _snippet(comment.body, needle)
        if snippet is not None:
            return snippet
    return None


def _project_stmt(pattern: str) -> Select[tuple[Project]]:
    return select(Project).where(
        or_(
            Project.key.ilike(pattern, escape="\\"),
            Project.name.ilike(pattern, escape="\\"),
            Project.description.ilike(pattern, escape="\\"),
        ),
    )


def _sprint_stmt(
    pattern: str,
    project_id: int | None,
) -> Select[tuple[Sprint, Project]]:
    stmt = (
        select(Sprint, Project)
        .join(Project, Sprint.project_id == Project.id)
        .where(
            or_(
                Sprint.name.ilike(pattern, escape="\\"),
                Sprint.goal.ilike(pattern, escape="\\"),
            ),
        )
    )
    if project_id is not None:
        stmt = stmt.where(Sprint.project_id == project_id)
    return stmt


def _user_stmt(pattern: str) -> Select[tuple[User]]:
    return select(User).where(User.display_name.ilike(pattern, escape="\\"))


def _contains(haystack: str, needle: str) -> bool:
    return needle.casefold() in haystack.casefold()


def _snippet(text: str, needle: str) -> str | None:
    if not text:
        return None
    index = text.casefold().find(needle.casefold())
    if index < 0:
        return None
    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(text), index + len(needle) + SNIPPET_RADIUS)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(text):
        excerpt = excerpt + "…"
    return excerpt
