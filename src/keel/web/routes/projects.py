from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.cadence import MAX_SPRINT_AHEAD
from keel.domain.enums import sprint_cadences_in_menu_order, statuses_in_workflow_order
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/projects")


@router.get("", response_class=HTMLResponse)
def project_list(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        "projects.html",
        page_context(
            request,
            chrome,
            projects=project_service.list_projects(session),
            error=error,
        ),
    )


@router.get("/{key}", response_class=HTMLResponse)
def project_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    issues = issue_service.list_issues(session, project.id)
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    return get_templates().TemplateResponse(
        request,
        "project.html",
        page_context(
            request,
            chrome,
            project=project,
            issues=issues,
            names=names,
            counts=issue_service.count_by_status(session, project.id),
            statuses=statuses_in_workflow_order(),
            cadences=sprint_cadences_in_menu_order(),
            max_sprint_ahead=MAX_SPRINT_AHEAD,
            error=error,
            notice=notice,
        ),
    )


@router.get("/{key}/issues/new")
def new_issue_page(key: str, error: str | None = None) -> RedirectResponse:
    """Creating happens on /create; keep the old per-project URL working."""
    params = {"project": key}
    if error:
        params["error"] = error
    return RedirectResponse(url=f"/create?{urlencode(params)}", status_code=303)
