from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from keel.domain.access import Permission
from keel.services import access as access_service
from keel.web.context import Chrome, get_templates, page_context

FORBIDDEN = "You are signed in, but this page is not allowed."


def forbidden_page(request: Request, chrome: Chrome) -> HTMLResponse:
    """The signed-in person opened something their roles do not allow."""
    return get_templates().TemplateResponse(
        request,
        "forbidden.html",
        page_context(request, chrome, forbidden_message=FORBIDDEN),
        status_code=403,
    )


def forbidden_response(request: Request) -> HTMLResponse:
    """The forbidden page when a route raises instead of returning it."""
    factory = request.app.state.session_factory
    with factory() as session:
        chrome = _chrome(request, session)
        rendered = (
            get_templates()
            .env.get_template("forbidden.html")
            .render(page_context(request, chrome, forbidden_message=FORBIDDEN))
        )
    return HTMLResponse(rendered, status_code=403)


def _chrome(request: Request, session: Session) -> Chrome:
    from keel.services import notifications as notification_service
    from keel.services import users as user_service
    from keel.services.access import load_access
    from keel.services.identity import SESSION_COOKIE, resolve_current_user

    current = resolve_current_user(
        session,
        authorization=request.headers.get("authorization"),
        session_cookie=request.cookies.get(SESSION_COOKIE),
        touch=False,
    )
    return Chrome(
        users=user_service.list_users(session),
        current_user=current,
        access=load_access(session, None if current is None else current.id),
        unread=(
            notification_service.has_unread(session, current.id)
            if current is not None
            else False
        ),
    )


def require_page(
    request: Request, chrome: Chrome, permission: str
) -> HTMLResponse | None:
    if chrome.access.allows(permission):
        return None
    return forbidden_page(request, chrome)


def require_project_page(
    request: Request,
    chrome: Chrome,
    session: Session,
    project_id: int,
    permission: Permission,
) -> HTMLResponse | None:
    """The forbidden page when this person lacks ``permission`` on the project."""
    if access_service.holds_project(session, chrome.access, project_id, permission):
        return None
    return forbidden_page(request, chrome)
