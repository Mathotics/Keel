from dataclasses import dataclass

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import IssueType, types_in_hierarchy_order
from keel.services import boards as board_service
from keel.services import labels as label_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter()
project_router = APIRouter(prefix="/projects")


@dataclass(frozen=True)
class _BoardQuery:
    types: list[IssueType]
    assignee_id: int | None
    unassigned: bool
    sprint_id: int | None
    unscheduled: bool
    label_name: str | None
    unlabeled: bool
    grouping: str | None
    selected_types: set[IssueType]
    selected_label: str
    selected_assignee: str
    selected_sprint: str


def _board_query(
    types: list[IssueType],
    assignee: str | None,
    sprint: str | None,
    label: str | None,
    by: str | None,
) -> _BoardQuery:
    assignee_id, unassigned = board_service.parse_assignee_filter(assignee)
    sprint_id, unscheduled = board_service.parse_sprint_filter(sprint)
    label_name, unlabeled = board_service.parse_label_filter(label)
    return _BoardQuery(
        types=types,
        assignee_id=assignee_id,
        unassigned=unassigned,
        sprint_id=sprint_id,
        unscheduled=unscheduled,
        label_name=label_name,
        unlabeled=unlabeled,
        grouping=board_service.parse_board_grouping(by),
        selected_types=set(types),
        selected_label="unlabeled" if unlabeled else (label_name or ""),
        selected_assignee=assignee.strip() if assignee else "",
        selected_sprint=sprint.strip() if sprint else "",
    )


@router.get("/board", response_class=HTMLResponse)
def master_board_page(
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    types: list[IssueType] = Query(default=[], alias="type"),
    project: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    sprint: str | None = Query(default=None),
    label: str | None = Query(default=None),
    by: str | None = Query(default=None),
    error: str | None = None,
) -> HTMLResponse:
    filters = _board_query(types, assignee, sprint, label, by)
    projects = list(project_service.list_projects(session))
    selected_project = board_service.parse_project_filter(project)
    project_id = None
    if selected_project:
        chosen = project_service.get_project_by_key(session, selected_project)
        project_id = chosen.id
        selected_project = chosen.key
    board = board_service.master_board(
        session,
        filters.types,
        project_id=project_id,
        assignee_id=filters.assignee_id,
        unassigned=filters.unassigned,
        sprint_id=filters.sprint_id,
        unscheduled=filters.unscheduled,
        label=filters.label_name,
        unlabeled=filters.unlabeled,
    )
    if project_id is not None:
        sprints = sprint_service.list_sprints(session, project_id)
    else:
        sprints = sprint_service.list_all_sprints(session)
    project_keys = {item.id: item.key for item in projects}
    return get_templates().TemplateResponse(
        request,
        "board.html",
        page_context(
            request,
            chrome,
            board=board,
            issue_types=types_in_hierarchy_order(),
            selected_types=filters.selected_types,
            selected_assignee=filters.selected_assignee,
            selected_sprint=filters.selected_sprint,
            selected_label=filters.selected_label,
            selected_project=selected_project or "",
            label_catalog=label_service.list_labels(session),
            separate_by_sprint=filters.grouping == "sprint",
            sprints=sprints,
            filter_projects=projects,
            project_keys=project_keys,
            prefix_sprints=True,
            has_projects=bool(projects),
            card_count=board_service.card_count(board),
            error=error,
        ),
    )


@project_router.get("/{key}/board", response_class=HTMLResponse)
def board_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    types: list[IssueType] = Query(default=[], alias="type"),
    assignee: str | None = Query(default=None),
    sprint: str | None = Query(default=None),
    label: str | None = Query(default=None),
    by: str | None = Query(default=None),
    error: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    filters = _board_query(types, assignee, sprint, label, by)
    board = board_service.project_board(
        session,
        project.id,
        filters.types,
        assignee_id=filters.assignee_id,
        unassigned=filters.unassigned,
        sprint_id=filters.sprint_id,
        unscheduled=filters.unscheduled,
        label=filters.label_name,
        unlabeled=filters.unlabeled,
    )
    return get_templates().TemplateResponse(
        request,
        "board.html",
        page_context(
            request,
            chrome,
            project=project,
            board=board,
            issue_types=types_in_hierarchy_order(),
            selected_types=filters.selected_types,
            selected_assignee=filters.selected_assignee,
            selected_sprint=filters.selected_sprint,
            selected_label=filters.selected_label,
            label_catalog=label_service.list_labels(session),
            separate_by_sprint=filters.grouping == "sprint",
            sprints=sprint_service.list_sprints(session, project.id),
            prefix_sprints=False,
            error=error,
        ),
    )
