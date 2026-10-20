from fastapi import Request
from fastapi.responses import HTMLResponse

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


def require_page(
    request: Request, chrome: Chrome, permission: str
) -> HTMLResponse | None:
    if chrome.access.allows(permission):
        return None
    return forbidden_page(request, chrome)
