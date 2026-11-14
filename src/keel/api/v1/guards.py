"""The signed-in person's access, and the project permission a route requires."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.domain.access import Permission
from keel.domain.errors import PermissionDeniedError
from keel.schemas.issue import IssueUpdate
from keel.services import access as access_service
from keel.services import projects as project_service
from keel.services.access import DENIED, Access

# Status, assignee, and sprint placement. Everything else is an edit.
_UPDATE_FIELDS = frozenset({"status", "assignee_id", "sprint_id"})


def current_access(session: SessionDep, acting: ActingUserDep) -> Access:
    """Who is calling. Anonymous callers are refused before a route runs."""
    if acting is None:
        raise PermissionDeniedError(DENIED)
    return access_service.load_access(session, acting.id)


AccessDep = Annotated[Access, Depends(current_access)]


def guard_project(
    session: Session,
    access: Access,
    project_id: int,
    permission: Permission,
) -> None:
    """404 when the project is missing, then require ``permission`` on it."""
    project_service.get_project(session, project_id)
    access_service.require_project(session, access, project_id, permission)


def guard_issue(
    session: Session,
    access: Access,
    issue_id: int,
    permission: Permission,
) -> int:
    """Require ``permission`` on the issue's project. Returns that project id."""
    project_id = access_service.project_of_issue(session, issue_id)
    access_service.require_project(session, access, project_id, permission)
    return project_id


def guard_issue_key(
    session: Session,
    access: Access,
    key: str,
    permission: Permission,
) -> int:
    project_id = access_service.project_of_issue_key(session, key)
    access_service.require_project(session, access, project_id, permission)
    return project_id


def guard_sprint(
    session: Session,
    access: Access,
    sprint_id: int,
    permission: Permission,
) -> int:
    project_id = access_service.project_of_sprint(session, sprint_id)
    access_service.require_project(session, access, project_id, permission)
    return project_id


def guard_series(
    session: Session,
    access: Access,
    series_id: int,
    permission: Permission,
) -> int:
    project_id = access_service.project_of_series(session, series_id)
    access_service.require_project(session, access, project_id, permission)
    return project_id


def permissions_for_issue_update(fields: set[str]) -> tuple[Permission, ...]:
    """Status, assignee, and sprint use update. Any other field uses edit."""
    if not fields:
        return (Permission.EDIT_ISSUES,)
    needed: list[Permission] = []
    if fields & _UPDATE_FIELDS:
        needed.append(Permission.UPDATE_ISSUES)
    if fields - _UPDATE_FIELDS:
        needed.append(Permission.EDIT_ISSUES)
    return tuple(needed)


def guard_other_project(
    session: Session,
    access: Access,
    source_project_id: int,
    target_project_id: int,
    permission: Permission,
) -> None:
    """A parent or sprint in another project needs that permission there too."""
    if target_project_id == source_project_id:
        return
    access_service.require_project(session, access, target_project_id, permission)


def require_project(permission: Permission) -> Callable[..., None]:
    def checker(project_id: int, session: SessionDep, access: AccessDep) -> None:
        guard_project(session, access, project_id, permission)

    return checker


def require_issue(permission: Permission) -> Callable[..., None]:
    def checker(issue_id: int, session: SessionDep, access: AccessDep) -> None:
        guard_issue(session, access, issue_id, permission)

    return checker


def require_issue_update(
    issue_id: int,
    payload: IssueUpdate,
    session: SessionDep,
    access: AccessDep,
) -> None:
    fields = set(payload.model_fields_set)
    project_id = access_service.project_of_issue(session, issue_id)
    for permission in permissions_for_issue_update(fields):
        access_service.require_project(session, access, project_id, permission)
    if "parent_id" in fields and payload.parent_id is not None:
        guard_other_project(
            session,
            access,
            project_id,
            access_service.project_of_issue(session, payload.parent_id),
            Permission.EDIT_ISSUES,
        )
    if "sprint_id" in fields and payload.sprint_id is not None:
        guard_other_project(
            session,
            access,
            project_id,
            access_service.project_of_sprint(session, payload.sprint_id),
            Permission.UPDATE_ISSUES,
        )


def require_comment_delete(
    comment_id: int,
    session: SessionDep,
    access: AccessDep,
) -> None:
    access_service.require_comment_delete(session, access, comment_id)


def require_dependency_delete(
    dependency_id: int,
    session: SessionDep,
    access: AccessDep,
) -> None:
    ends = access_service.project_of_dependency(session, dependency_id)
    access_service.require_dependency_projects(
        session,
        access,
        ends.source_project_id,
        ends.target_project_id,
    )


def guard_comment(
    session: Session,
    access: Access,
    comment_id: int,
    permission: Permission,
) -> int:
    project_id = access_service.project_of_comment(session, comment_id)
    access_service.require_project(session, access, project_id, permission)
    return project_id
