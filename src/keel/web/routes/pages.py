from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.enums import IssueType, types_in_hierarchy_order
from keel.paths import license_text
from keel.services import projects as project_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter()

# Temporary on purpose. A permanent redirect would be cached by browsers and
# outlive the day `/` becomes a dashboard rather than a signpost to the list.
FOUND = 302


@router.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    """The entry point, kept separate from the project list it points at."""
    return RedirectResponse(url="/projects", status_code=FOUND)


@router.get("/create", response_class=HTMLResponse)
def create_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    project: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    projects = project_service.list_projects(session)
    chosen = None
    if project:
        chosen = project_service.get_project_by_key(session, project)
    elif len(projects) == 1:
        chosen = projects[0]
    return get_templates().TemplateResponse(
        request,
        "create.html",
        page_context(
            request,
            chrome,
            projects=projects,
            project=chosen,
            issue_types=types_in_hierarchy_order(),
            default_type=IssueType.STORY,
            error=error,
        ),
    )


@router.get("/license", response_class=HTMLResponse)
def license_page(request: Request, chrome: ChromeDep) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "license.html",
        page_context(request, chrome, license_text=license_text()),
    )
