from collections.abc import Sequence

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.db.models import Sprint
from keel.domain.enums import sprint_states_in_lifecycle_order
from keel.domain.errors import NotFoundError
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/projects")


@router.get("/{key}/sprints", response_class=HTMLResponse)
def sprints_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    found = sprint_service.list_sprints(session, project.id)
    grouped: dict[str, Sequence[Sprint]] = {
        state.value: [sprint for sprint in found if sprint.state is state]
        for state in sprint_states_in_lifecycle_order()
    }
    return get_templates().TemplateResponse(
        request,
        "sprints.html",
        page_context(
            request,
            chrome,
            project=project,
            grouped=grouped,
            states=sprint_states_in_lifecycle_order(),
            error=error,
            notice=notice,
        ),
    )


@router.get("/{key}/sprints/{sprint_id}", response_class=HTMLResponse)
def sprint_detail_page(
    key: str,
    sprint_id: int,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    sprint = sprint_service.get_sprint(session, sprint_id)
    if sprint.project_id != project.id:
        raise NotFoundError(f"No sprint {sprint_id} in {project.key}.")
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    return get_templates().TemplateResponse(
        request,
        "sprint_detail.html",
        page_context(
            request,
            chrome,
            project=project,
            sprint=sprint,
            issues=sprint_service.list_sprint_issues(session, sprint.id),
            names=names,
            error=error,
            notice=notice,
        ),
    )
