from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.access import (
    PROJECT_PERMISSIONS,
    ROLE_PERMISSIONS,
    ROLE_SCOPE,
    Permission,
    RoleCode,
    Scope,
    parse_permission,
    parse_role,
)
from keel.domain.errors import DomainError
from keel.services import access as access_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.forbid import forbidden_page

router = APIRouter()
SEE_OTHER = 303
_PROJECT_ROLES: tuple[RoleCode, ...] = (
    RoleCode.VIEWER,
    RoleCode.CONTRIBUTOR,
    RoleCode.PROJECT_OWNER,
)


@dataclass(frozen=True)
class _PersonGrant:
    user_id: int
    username: str
    display_name: str
    role: str
    direct_codes: frozenset[str]


def _role_bundles() -> dict[str, str]:
    return {
        role.value: " ".join(
            permission.value
            for permission in PROJECT_PERMISSIONS
            if permission in ROLE_PERMISSIONS[role]
        )
        for role in _PROJECT_ROLES
    }


def _parse_project_role(code: str) -> RoleCode | None:
    if not code:
        return None
    role = parse_role(code)
    if role is None or ROLE_SCOPE[role] is not Scope.PROJECT:
        return None
    return role


def _submitted(permission: list[str] | None) -> frozenset[Permission]:
    found: set[Permission] = set()
    for code in permission or []:
        parsed = parse_permission(code)
        if parsed is not None:
            found.add(parsed)
    return frozenset(found)


@router.get("/projects/{key}/access", response_class=HTMLResponse)
def project_access_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    if not access_service.holds_project(
        session, chrome.access, project.id, Permission.VIEW_PROJECT_RBAC
    ):
        return forbidden_page(request, chrome)
    roles, permissions = access_service.access_catalog()
    shared_role = access_service.everyone_role(session, project.id)
    people = [
        _PersonGrant(
            user_id=person.id,
            username=person.username,
            display_name=person.display_name,
            role=(
                held.value
                if (held := access_service.project_role(session, person.id, project.id))
                is not None
                else ""
            ),
            direct_codes=frozenset(
                permission.value
                for permission in access_service.project_direct(
                    session, person.id, project.id
                )
            ),
        )
        for person in user_service.list_users(session)
    ]
    return get_templates().TemplateResponse(
        request,
        "project_access.html",
        page_context(
            request,
            chrome,
            project=project,
            people=people,
            everyone_role=shared_role.value if shared_role is not None else "",
            everyone_direct_codes=frozenset(
                permission.value
                for permission in access_service.everyone_direct(session, project.id)
            ),
            project_roles=[
                (role.value, access_service.role_label(role)) for role in _PROJECT_ROLES
            ],
            role_bundles=_role_bundles(),
            permission_choices=access_service.project_permission_choices(),
            catalog_roles=[role for role in roles if role.scope == "Project"],
            catalog_permissions=[
                permission
                for permission in permissions
                if permission.scope == "Project"
            ],
            can_manage=access_service.holds_project(
                session, chrome.access, project.id, Permission.MANAGE_PROJECT_RBAC
            ),
            error=error,
        ),
    )


@router.post("/web/projects/{project_id}/access/everyone", response_model=None)
def save_everyone_access(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    project_id: int,
    role: Annotated[str, Form()] = "",
    permission: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse | RedirectResponse:
    project = project_service.get_project(session, project_id)
    try:
        access_service.save_everyone_grant(
            session,
            chrome.access,
            project.id,
            role=_parse_project_role(role),
            submitted_direct=_submitted(permission),
        )
    except DomainError as exc:
        session.rollback()
        return RedirectResponse(
            f"/projects/{project.key}/access?" + urlencode({"error": exc.message}),
            status_code=SEE_OTHER,
        )
    return RedirectResponse(f"/projects/{project.key}/access", status_code=SEE_OTHER)


@router.post("/web/projects/{project_id}/access/{user_id}", response_model=None)
def save_person_access(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    project_id: int,
    user_id: int,
    role: Annotated[str, Form()] = "",
    permission: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse | RedirectResponse:
    project = project_service.get_project(session, project_id)
    try:
        access_service.save_project_grant(
            session,
            chrome.access,
            project.id,
            user_id,
            role=_parse_project_role(role),
            submitted_direct=_submitted(permission),
        )
    except DomainError as exc:
        session.rollback()
        return RedirectResponse(
            f"/projects/{project.key}/access?" + urlencode({"error": exc.message}),
            status_code=SEE_OTHER,
        )
    return RedirectResponse(f"/projects/{project.key}/access", status_code=SEE_OTHER)
