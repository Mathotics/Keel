from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.access import Permission
from keel.web.context import ChromeDep, get_templates, page_context
from keel.web.forbid import require_page

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    chrome: ChromeDep,
    error: str | None = None,
) -> HTMLResponse:
    denied = require_page(request, chrome, Permission.VIEW_USERS.value)
    if denied is not None:
        return denied
    return get_templates().TemplateResponse(
        request,
        "users.html",
        page_context(request, chrome, error=error),
    )
