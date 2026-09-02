"""Lookup from the top-bar find field: exact jumps, then a short list per kind."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import String, cast, func, literal, or_, select
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


@dataclass(frozen=True)
class IssueHit:
    key: str
    title: str
    type: IssueType
    project_key: str
    snippet: str | None


@dataclass(frozen=True)
class ProjectHit:
    key: str
    name: str
    snippet: str | None


@dataclass(frozen=True)
class SprintHit:
    id: int
    name: str
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
        return FindJump(url=f"/issues/{issue_service.issue_key(issue, project)}")
    if KEY_PATTERN.fullmatch(needle.upper()):
        try:
            named = project_service.get_project_by_key(session, needle)
        except NotFoundError:
            named = None
        if named is not None:
            return FindJump(url=f"/projects/{named.key}")
    users = session.scalars(
        select(User).where(func.lower(User.display_name) == needle.lower()),
    ).all()
    if len(users) == 1:
        return FindJump(url="/users")
    sprints = _sprints_named(session, needle, project_id)
    if len(sprints) == 1:
        sprint = sprints[0]
        project = project_service.get_project(session, sprint.project_id)
        return FindJump(url=f"/projects/{project.key}/sprints/{sprint.id}")
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


def _list_matches(
    session: Session,
    needle: str,
    project_id: int | None,
) -> FindResults:
    pattern = _like_pattern(needle)
    issues, issues_more = _issue_hits(session, needle, pattern, project_id)
    projects, projects_more = _project_hits(session, needle, pattern)
    sprints, sprints_more = _sprint_hits(session, needle, pattern, project_id)
    users, users_more = _user_hits(session, pattern)
    return FindResults(
        query=needle,
        issues=issues,
        issues_more=issues_more,
        projects=projects,
        projects_more=projects_more,
        sprints=sprints,
        sprints_more=sprints_more,
        users=users,
        users_more=users_more,
    )


def _like_pattern(needle: str) -> str:
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _issue_key_expr() -> ColumnElement[str]:
    return Project.key.concat(literal("-")).concat(cast(Issue.number, String))


def _issue_hits(
    session: Session,
    needle: str,
    pattern: str,
    project_id: int | None,
) -> tuple[list[IssueHit], bool]:
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
                _issue_key_expr().ilike(pattern, escape="\\"),
                Issue.id.in_(comment_ids),
            ),
        )
    )
    if project_id is not None:
        stmt = stmt.where(Issue.project_id == project_id)
    rows = session.execute(
        stmt.order_by(Project.key, Issue.number).limit(PER_KIND + 1),
    ).all()
    more = len(rows) > PER_KIND
    hits = []
    for issue, project in rows[:PER_KIND]:
        hits.append(
            IssueHit(
                key=issue_service.issue_key(issue, project),
                title=issue.title,
                type=issue.type,
                project_key=project.key,
                snippet=_issue_snippet(session, issue, project, needle),
            ),
        )
    return hits, more


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
    comments = session.scalars(
        select(Comment).where(Comment.issue_id == issue.id).order_by(Comment.id),
    )
    for comment in comments:
        snippet = _snippet(comment.body, needle)
        if snippet is not None:
            return snippet
    return None


def _project_hits(
    session: Session,
    needle: str,
    pattern: str,
) -> tuple[list[ProjectHit], bool]:
    rows = session.scalars(
        select(Project)
        .where(
            or_(
                Project.key.ilike(pattern, escape="\\"),
                Project.name.ilike(pattern, escape="\\"),
                Project.description.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Project.key)
        .limit(PER_KIND + 1),
    ).all()
    more = len(rows) > PER_KIND
    hits = []
    for project in rows[:PER_KIND]:
        snippet = None
        if not _contains(project.key, needle) and not _contains(project.name, needle):
            snippet = _snippet(project.description, needle)
        hits.append(ProjectHit(key=project.key, name=project.name, snippet=snippet))
    return hits, more


def _sprint_hits(
    session: Session,
    needle: str,
    pattern: str,
    project_id: int | None,
) -> tuple[list[SprintHit], bool]:
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
    rows = session.execute(
        stmt.order_by(Project.key, Sprint.id).limit(PER_KIND + 1),
    ).all()
    more = len(rows) > PER_KIND
    hits = []
    for sprint, project in rows[:PER_KIND]:
        snippet = None
        if not _contains(sprint.name, needle):
            snippet = _snippet(sprint.goal, needle)
        hits.append(
            SprintHit(
                id=sprint.id,
                name=sprint.name,
                project_key=project.key,
                snippet=snippet,
            ),
        )
    return hits, more


def _user_hits(session: Session, pattern: str) -> tuple[list[UserHit], bool]:
    rows = session.scalars(
        select(User)
        .where(User.display_name.ilike(pattern, escape="\\"))
        .order_by(User.display_name)
        .limit(PER_KIND + 1),
    ).all()
    more = len(rows) > PER_KIND
    return [UserHit(display_name=user.display_name) for user in rows[:PER_KIND]], more


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
