from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from keel.db.models import Sprint
from keel.domain.enums import (
    SprintCadence,
    SprintState,
    sprint_states_in_lifecycle_order,
)
from keel.domain.errors import NotFoundError
from keel.services import auto_sprint
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.paging import (
    DEFAULT_ISSUE_PAGE_SIZE,
    ISSUE_PAGE_SIZES,
    PageWindow,
    issue_page,
)

router = APIRouter(prefix="/projects")


@dataclass(frozen=True)
class _SprintTable:
    key: str
    state: SprintState
    sprints: Sequence[Sprint]
    pager: PageWindow
    first_href: str
    previous_href: str
    next_href: str
    last_href: str


def _sprint_href(
    project_key: str,
    pagers: dict[str, PageWindow],
    focus: str,
    page: int,
) -> str:
    """One table moves. The other tables keep the page they are already on."""
    pairs: list[tuple[str, int]] = []
    for name, window in pagers.items():
        pairs.append((f"{name}_page", page if name == focus else window.page))
        pairs.append((f"{name}_size", window.page_size))
    return f"/projects/{project_key}/sprints?{urlencode(pairs)}"


@router.get("/{key}/sprints", response_class=HTMLResponse)
def sprints_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    error: str | None = None,
    notice: str | None = None,
    planned_page: int = 1,
    planned_size: int = DEFAULT_ISSUE_PAGE_SIZE,
    active_page: int = 1,
    active_size: int = DEFAULT_ISSUE_PAGE_SIZE,
    completed_page: int = 1,
    completed_size: int = DEFAULT_ISSUE_PAGE_SIZE,
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
    pagers = {
        state.value: issue_page(len(grouped[state.value]), *requested[state.value])
        for state in states
    }
    tables = [
        _sprint_table(project.key, state, grouped[state.value], pagers)
        for state in states
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
            page_sizes=ISSUE_PAGE_SIZES,
            auto_sprint_on=auto_on,
            cadence_label=auto_sprint.cadence_label(project) if auto_on else None,
            sprint_ahead=project.sprint_ahead if auto_on else 0,
            next_close=None if active is None else active.ends_on,
            error=error,
            notice=shown_notice,
        ),
    )


def _sprint_table(
    project_key: str,
    state: SprintState,
    rows: Sequence[Sprint],
    pagers: dict[str, PageWindow],
) -> _SprintTable:
    pager = pagers[state.value]
    return _SprintTable(
        key=state.value,
        state=state,
        sprints=rows[pager.offset : pager.offset + pager.page_size],
        pager=pager,
        first_href=_sprint_href(project_key, pagers, state.value, 1),
        previous_href=_sprint_href(
            project_key, pagers, state.value, max(pager.page - 1, 1)
        ),
        next_href=_sprint_href(project_key, pagers, state.value, pager.page + 1),
        last_href=_sprint_href(project_key, pagers, state.value, pager.pages),
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
