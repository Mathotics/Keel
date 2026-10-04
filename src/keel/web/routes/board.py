from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from keel.services import boards as board_service
from keel.services import projects as project_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context
from keel.web.filters import (
    FilterRequest,
    filter_context,
    filter_request,
    layout_pairs,
    read_bar,
    sprint_menu,
)

router = APIRouter()
project_router = APIRouter(prefix="/projects")


def _render(
    request: Request,
    chrome: ChromeDep,
    session: Session,
    raw: FilterRequest,
    *,
    action: str,
    project_id: int | None,
    show_project: bool,
    prefix: bool,
    by: list[str],
    error: str | None,
    project: object,
    has_projects: bool,
) -> HTMLResponse:
    grouping = board_service.parse_board_grouping(by)
    bar = read_bar(
        session,
        raw,
        base=action,
        include_projects=show_project,
        extra=layout_pairs(grouping),
    )
    criteria = replace(bar.criteria, hide_closed_in_completed_sprints=True)
    if project_id is None:
        board = board_service.master_board(session, filters=criteria)
        projects = list(project_service.list_projects(session))
        project_keys = {item.id: item.key for item in projects}
        has_projects = bool(projects)
    else:
        board = board_service.project_board(session, project_id, filters=criteria)
        project_keys = {}
    sprints = sprint_menu(
        session,
        project_id=project_id,
        project_ids=criteria.project_ids,
    )
    return get_templates().TemplateResponse(
        request,
        "board.html",
        page_context(
            request,
            chrome,
            project=project,
            board=board,
            has_projects=has_projects,
            card_count=board_service.card_count(board),
            **filter_context(
                bar,
                action=action,
                show_project=show_project,
                show_layout=True,
                sprints=sprints,
                project_keys=project_keys,
                prefix=prefix,
                separate=grouping == "sprint",
                preserve=(),
                error=error,
            ),
        ),
    )


@router.get("/board", response_class=HTMLResponse)
def master_board_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: Annotated[FilterRequest, Depends(filter_request)],
    by: list[str] = Query(default=[]),
    error: str | None = None,
) -> HTMLResponse:
    return _render(
        request,
        chrome,
        session,
        raw,
        action="/board",
        project_id=None,
        show_project=True,
        prefix=True,
        by=by,
        error=error,
        project=None,
        has_projects=False,
    )


@project_router.get("/{key}/board", response_class=HTMLResponse)
def board_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    raw: Annotated[FilterRequest, Depends(filter_request)],
    by: list[str] = Query(default=[]),
    error: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    return _render(
        request,
        chrome,
        session,
        raw,
        action=f"/projects/{project.key}/board",
        project_id=project.id,
        show_project=False,
        prefix=False,
        by=by,
        error=error,
        project=project,
        has_projects=True,
    )
