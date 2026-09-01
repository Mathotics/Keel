from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.web.context import ChromeDep, get_templates, page_context

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    chrome: ChromeDep,
    error: str | None = None,
) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "users.html",
        page_context(request, chrome, error=error),
    )
