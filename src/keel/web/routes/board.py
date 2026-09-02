from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from keel.domain.enums import IssueType, types_in_hierarchy_order
from keel.services import boards as board_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter(prefix="/projects")


@router.get("/{key}/board", response_class=HTMLResponse)
def board_page(
    key: str,
    request: Request,
    chrome: ChromeDep,
    session: SessionDep,
    types: list[IssueType] = Query(default=[], alias="type"),
    assignee: str | None = Query(default=None),
    sprint: str | None = Query(default=None),
    by: str | None = Query(default=None),
    error: str | None = None,
) -> HTMLResponse:
    project = project_service.get_project_by_key(session, key)
    assignee_id, unassigned = board_service.parse_assignee_filter(assignee)
    sprint_id, unscheduled = board_service.parse_sprint_filter(sprint)
    grouping = board_service.parse_board_grouping(by)
    board = board_service.project_board(
        session,
        project.id,
        types,
        assignee_id=assignee_id,
        unassigned=unassigned,
        sprint_id=sprint_id,
        unscheduled=unscheduled,
    )
    selected = set(types)
    return get_templates().TemplateResponse(
        request,
        "board.html",
        page_context(
            request,
            chrome,
            project=project,
            board=board,
            issue_types=types_in_hierarchy_order(),
            selected_types=selected,
            selected_assignee=assignee.strip() if assignee else "",
            selected_sprint=sprint.strip() if sprint else "",
            separate_by_sprint=grouping == "sprint",
            sprints=sprint_service.list_sprints(session, project.id),
            error=error,
        ),
    )
