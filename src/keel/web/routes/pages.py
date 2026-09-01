from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.paths import license_text
from keel.web.context import ChromeDep, get_templates, page_context

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, chrome: ChromeDep) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "home.html",
        page_context(request, chrome),
    )


@router.get("/license", response_class=HTMLResponse)
def license_page(request: Request, chrome: ChromeDep) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "license.html",
        page_context(request, chrome, license_text=license_text()),
    )
