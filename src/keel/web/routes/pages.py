from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.paths import license_text
from keel.web.context import ChromeDep, get_templates, page_context

router = APIRouter()

# Temporary on purpose. A permanent redirect would be cached by browsers and
# outlive the day `/` becomes a dashboard rather than a signpost to the list.
FOUND = 302


@router.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    """The entry point, kept separate from the project list it points at."""
    return RedirectResponse(url="/projects", status_code=FOUND)


@router.get("/license", response_class=HTMLResponse)
def license_page(request: Request, chrome: ChromeDep) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "license.html",
        page_context(request, chrome, license_text=license_text()),
    )
