from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.errors import NotFoundError
from keel.services import notifications as notification_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.routes.forms import _back

router = APIRouter()
SEE_OTHER = 303


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(
    request: Request,
    session: SessionDep,
    chrome: ChromeDep,
    error: str | None = None,
) -> HTMLResponse:
    user = chrome.current_user
    assert user is not None
    notices = notification_service.list_notices(session, user.id)
    return get_templates().TemplateResponse(
        request,
        "notifications.html",
        page_context(request, chrome, notices=notices, error=error),
    )


@router.post("/web/notifications/{notice_id}/open")
def open_notification(
    notice_id: int,
    session: SessionDep,
    chrome: ChromeDep,
) -> RedirectResponse:
    """Mark this notice read, then open its issue when the issue still exists."""
    user = chrome.current_user
    assert user is not None
    try:
        notice = notification_service.mark_read(session, user.id, notice_id)
    except NotFoundError as exc:
        session.rollback()
        return _back("/notifications", exc.message)
    if notice.issue_id is None:
        return RedirectResponse("/notifications", status_code=SEE_OTHER)
    return RedirectResponse(f"/issues/{notice.issue_key}", status_code=SEE_OTHER)


@router.post("/web/notifications/{notice_id}/delete")
def delete_notification(
    notice_id: int,
    session: SessionDep,
    chrome: ChromeDep,
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    try:
        notification_service.delete_notice(session, user.id, notice_id)
    except NotFoundError as exc:
        session.rollback()
        return _back("/notifications", exc.message)
    return RedirectResponse("/notifications", status_code=SEE_OTHER)
