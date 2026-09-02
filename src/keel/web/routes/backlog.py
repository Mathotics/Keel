from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import SprintState
from keel.services import backlog as backlog_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/projects")


@router.get("/{key}/backlog", response_class=HTMLResponse)
def backlog_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    return get_templates().TemplateResponse(
        request,
        "backlog.html",
        page_context(
            request,
            chrome,
            project=project,
            issues=backlog_service.project_backlog(session, project.id),
            names=names,
            planned=sprint_service.list_sprints(
                session,
                project.id,
                SprintState.PLANNED,
            ),
            error=error,
        ),
    )
