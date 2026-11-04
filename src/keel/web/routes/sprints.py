from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.db.models import Sprint
from keel.domain.enums import (
    SprintCadence,
    SprintState,
    label,
    sprint_states_in_lifecycle_order,
)
from keel.domain.errors import NotFoundError
from keel.services import auto_sprint
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.paging import (
    DEFAULT_PAGE_SIZE,
    PagerRequest,
    TablePager,
    one_pager,
    page_rows,
    table_pagers,
)

router = APIRouter(prefix="/projects")


@dataclass(frozen=True)
class _SprintTable:
    state: SprintState
    sprints: Sequence[Sprint]
    pager: TablePager


@router.get("/{key}/sprints", response_class=HTMLResponse)
def sprints_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
    planned_page: int = 1,
    planned_size: int = DEFAULT_PAGE_SIZE,
    active_page: int = 1,
    active_size: int = DEFAULT_PAGE_SIZE,
    completed_page: int = 1,
    completed_size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    found = sprint_service.list_sprints(session, project.id)
    states = sprint_states_in_lifecycle_order()
    grouped: dict[str, Sequence[Sprint]] = {
        state.value: [sprint for sprint in found if sprint.state is state]
        for state in states
    }
    requested = {
        SprintState.PLANNED.value: (planned_page, planned_size),
        SprintState.ACTIVE.value: (active_page, active_size),
        SprintState.COMPLETED.value: (completed_page, completed_size),
    }
    pagers = table_pagers(
        f"/projects/{project.key}/sprints",
        [
            PagerRequest(
                label="Sprints per page",
                field_id=f"sprint-size-{state.value}",
                aria_label=f"{label(state)} pages",
                empty="0 sprints",
                total=len(grouped[state.value]),
                page=requested[state.value][0],
                size=requested[state.value][1],
                key=state.value,
            )
            for state in states
        ],
    )
    tables = [
        _SprintTable(
            state=state,
            sprints=page_rows(grouped[state.value], pager.window),
            pager=pager,
        )
        for state, pager in zip(states, pagers, strict=True)
    ]
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
            tables=tables,
            auto_sprint_on=auto_on,
            cadence_label=auto_sprint.cadence_label(project) if auto_on else None,
            sprint_ahead=project.sprint_ahead if auto_on else 0,
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
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    sprint = sprint_service.get_sprint(session, sprint_id)
    if sprint.project_id != project.id:
        raise NotFoundError(f"No sprint {sprint_id} in {project.key}.")
    found = sprint_service.list_sprint_issues(session, sprint.id)
    pager = one_pager(
        f"/projects/{project.key}/sprints/{sprint.id}",
        PagerRequest(
            label="Issues per page",
            field_id="sprint-issue-size",
            aria_label="Sprint issue pages",
            empty="0 issues",
            total=len(found),
            page=page,
            size=size,
        ),
    )
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    return get_templates().TemplateResponse(
        request,
        "sprint_detail.html",
        page_context(
            request,
            chrome,
            project=project,
            sprint=sprint,
            issues=page_rows(found, pager.window),
            names=names,
            pager=pager,
            error=error,
            notice=notice,
        ),
    )
