from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.access import Permission
from keel.web.context import ChromeDep, get_templates, page_context
from keel.web.forbid import require_page
from keel.web.paging import DEFAULT_PAGE_SIZE, PagerRequest, one_pager, page_rows

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    chrome: ChromeDep,
    error: str | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    denied = require_page(request, chrome, Permission.VIEW_USERS.value)
    if denied is not None:
        return denied
    pager = one_pager(
        "/users",
        PagerRequest(
            label="Users per page",
            field_id="user-list-size",
            aria_label="User pages",
            empty="0 users",
            total=len(chrome.users),
            page=page,
            size=size,
        ),
    )
    return get_templates().TemplateResponse(
        request,
        "users.html",
        page_context(
            request,
            chrome,
            users=page_rows(chrome.users, pager.window),
            pager=pager,
            error=error,
        ),
    )
