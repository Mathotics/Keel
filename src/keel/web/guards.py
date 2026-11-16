"""Web dependencies that refuse a project action before the handler runs."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from keel.domain.access import Permission
from keel.domain.errors import PermissionDeniedError
from keel.services import access as access_service
from keel.services import projects as project_service
from keel.services.access import DENIED
from keel.web.context import Chrome, ChromeDep, SessionDep


def _require(
    session: Session,
    chrome: Chrome,
    project_id: int,
    permission: Permission,
) -> None:
    if access_service.holds_project(session, chrome.access, project_id, permission):
        return
    raise PermissionDeniedError(DENIED)


def require_issue(permission: Permission) -> Callable[..., None]:
    """Depend on this so an issue route checks the issue's project."""

    def checker(issue_id: int, session: SessionDep, chrome: ChromeDep) -> None:
        _require(
            session,
            chrome,
            access_service.project_of_issue(session, issue_id),
            permission,
        )

    return checker


def require_project(permission: Permission) -> Callable[..., None]:
    def checker(project_id: int, session: SessionDep, chrome: ChromeDep) -> None:
        project_service.get_project(session, project_id)
        _require(session, chrome, project_id, permission)

    return checker


def require_project_key(permission: Permission) -> Callable[..., None]:
    def checker(key: str, session: SessionDep, chrome: ChromeDep) -> None:
        project = project_service.get_project_by_key(session, key)
        _require(session, chrome, project.id, permission)

    return checker


def require_comment_delete() -> Callable[..., None]:
    def checker(comment_id: int, session: SessionDep, chrome: ChromeDep) -> None:
        access_service.require_comment_delete(session, chrome.access, comment_id)

    return checker


def require_dependency_delete() -> Callable[..., None]:
    def checker(dependency_id: int, session: SessionDep, chrome: ChromeDep) -> None:
        ends = access_service.project_of_dependency(session, dependency_id)
        access_service.require_dependency_projects(
            session,
            chrome.access,
            ends.source_project_id,
            ends.target_project_id,
        )

    return checker


def require_series(permission: Permission) -> Callable[..., None]:
    def checker(series_id: int, session: SessionDep, chrome: ChromeDep) -> None:
        _require(
            session,
            chrome,
            access_service.project_of_series(session, series_id),
            permission,
        )

    return checker


def require_sprint(permission: Permission) -> Callable[..., None]:
    def checker(sprint_id: int, session: SessionDep, chrome: ChromeDep) -> None:
        _require(
            session,
            chrome,
            access_service.project_of_sprint(session, sprint_id),
            permission,
        )

    return checker


def require_issue_key(permission: Permission) -> Callable[..., None]:
    def checker(key: str, session: SessionDep, chrome: ChromeDep) -> None:
        _require(
            session,
            chrome,
            access_service.project_of_issue_key(session, key),
            permission,
        )

    return checker
