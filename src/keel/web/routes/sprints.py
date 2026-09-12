from collections.abc import Sequence

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.db.models import Sprint
from keel.domain.enums import SprintCadence, sprint_states_in_lifecycle_order
from keel.domain.errors import NotFoundError
from keel.services import auto_sprint
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
    auto_on = project.sprint_cadence is not SprintCadence.OFF
    active = sprint_service.active_sprint(session, project.id) if auto_on else None
    shown_notice = notice or (project.auto_sprint_notice or None)
    return get_templates().TemplateResponse(
        request,
        "sprints.html",
        page_context(
            request,
            chrome,
            project=project,
            grouped=grouped,
            states=sprint_states_in_lifecycle_order(),
            auto_sprint_on=auto_on,
            cadence_label=auto_sprint.cadence_label(project) if auto_on else None,
            next_close=None if active is None else active.ends_on,
            error=error,
            notice=shown_notice,
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
