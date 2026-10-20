from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.access import Permission, parse_permission
from keel.domain.errors import DomainError
from keel.services import access as access_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.forbid import require_page

router = APIRouter()
SEE_OTHER = 303


@dataclass(frozen=True)
class _GrantView:
    user_id: int
    username: str
    display_name: str
    role_codes: frozenset[str]
    direct_codes: frozenset[str]
    role_names: str


@router.get("/admin/access", response_class=HTMLResponse)
def access_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    denied = require_page(request, chrome, Permission.VIEW_GLOBAL_RBAC.value)
    if denied is not None:
        return denied
    grants = [
        _GrantView(
            user_id=grant.user_id,
            username=grant.username,
            display_name=grant.display_name,
            role_codes=frozenset(role.value for role in grant.roles),
            direct_codes=frozenset(permission.value for permission in grant.direct),
            role_names=", ".join(
                access_service.role_label(role) for role in sorted(grant.roles)
            ),
        )
        for grant in access_service.global_grants(session)
    ]
    return get_templates().TemplateResponse(
        request,
        "access.html",
        page_context(
            request,
            chrome,
            grants=grants,
            permission_choices=access_service.permission_choices(),
            can_manage=chrome.access.allows(Permission.MANAGE_GLOBAL_RBAC.value),
            actor_is_owner=chrome.access.is_owner,
            error=error,
        ),
    )


@router.post("/web/access/{user_id}", response_model=None)
def save_access(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    user_id: int,
    owner: Annotated[str, Form()] = "",
    admin: Annotated[str, Form()] = "",
    permission: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse | RedirectResponse:
    denied = require_page(request, chrome, Permission.MANAGE_GLOBAL_RBAC.value)
    if denied is not None:
        return denied
    submitted: set[Permission] = set()
    for code in permission or []:
        parsed = parse_permission(code)
        if parsed is not None:
            submitted.add(parsed)
    try:
        access_service.save_global_grant(
            session,
            chrome.access,
            user_id,
            requested_owner=owner == "1",
            requested_admin=admin == "1",
            submitted_direct=frozenset(submitted),
        )
    except DomainError as exc:
        session.rollback()
        return RedirectResponse(
            "/admin/access?" + urlencode({"error": exc.message}),
            status_code=SEE_OTHER,
        )
    return RedirectResponse("/admin/access", status_code=SEE_OTHER)
