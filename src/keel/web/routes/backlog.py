from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.services import backlog as backlog_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.paging import DEFAULT_PAGE_SIZE, PagerRequest, one_pager, page_rows

router = APIRouter(prefix="/projects")


@router.get("/{key}/backlog", response_class=HTMLResponse)
def backlog_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    backlog = backlog_service.project_backlog(session, project.id)
    pager = one_pager(
        f"/projects/{project.key}/backlog",
        PagerRequest(
            label="Issues per page",
            field_id="backlog-issue-size",
            aria_label="Backlog pages",
            empty="0 issues",
            total=len(backlog),
            page=page,
            size=size,
        ),
    )
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    return get_templates().TemplateResponse(
        request,
        "backlog.html",
        page_context(
            request,
            chrome,
            project=project,
            issues=page_rows(backlog, pager.window),
            names=names,
            sprints=sprint_service.list_assignable_sprints(session, project.id),
            pager=pager,
            error=error,
        ),
    )
