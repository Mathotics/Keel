"""The signed-in person's access, and the project permission a route requires."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.domain.access import Permission
from keel.domain.errors import PermissionDeniedError
from keel.services import access as access_service
from keel.services import projects as project_service
from keel.services.access import DENIED, Access


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


def guard_comment(
    session: Session,
    access: Access,
    comment_id: int,
    permission: Permission,
) -> int:
    project_id = access_service.project_of_comment(session, comment_id)
    access_service.require_project(session, access, project_id, permission)
    return project_id
