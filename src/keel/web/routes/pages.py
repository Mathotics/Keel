from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import (
    IssuePriority,
    IssueStatus,
    IssueType,
    priorities_in_rank_order,
    statuses_in_workflow_order,
    types_in_hierarchy_order,
)
from keel.paths import license_text
from keel.services import home as home_service
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    """Personal inbox for the acting user; `/projects` stays the directory."""
    inbox = home_service.HomeInbox()
    if chrome.current_user is not None:
        inbox = home_service.personal_inbox(session, chrome.current_user.id)
    return get_templates().TemplateResponse(
        request,
        "home.html",
        page_context(
            request,
            chrome,
            inbox=inbox,
            has_projects=bool(project_service.list_projects(session)),
            statuses=statuses_in_workflow_order(),
            error=error,
        ),
    )


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
    parents = []
    sprints = []
    if chosen is not None:
        parents = list(issue_service.list_issues(session, chosen.id))
        sprints = list(sprint_service.list_sprints(session, chosen.id))
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
            statuses=statuses_in_workflow_order(),
            default_status=IssueStatus.TODO,
            priorities=priorities_in_rank_order(),
            default_priority=IssuePriority.P3,
            parents=parents,
            sprints=sprints,
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
