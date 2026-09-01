from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import statuses_in_workflow_order
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
            error=error,
        ),
    )


@router.get("/{key}/issues/new", response_class=HTMLResponse)
def new_issue_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    return get_templates().TemplateResponse(
        request,
        "issue_form.html",
        page_context(
            request,
            chrome,
            project=project,
            issue=None,
            parents=issue_service.list_issues(session, project.id),
            assignees=user_service.list_users(session),
            error=error,
        ),
    )
