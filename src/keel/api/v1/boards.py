from fastapi import APIRouter, Query

from keel.api.v1.deps import SessionDep
from keel.domain.enums import IssueType, label
from keel.schemas.board import BoardColumnRead, BoardRead
from keel.schemas.issue import IssueRead
from keel.services import backlog as backlog_service
from keel.services import boards as board_service
from keel.services import projects as project_service

router = APIRouter(tags=["boards"])


@router.get("/projects/{project_id}/board", response_model=BoardRead)
def read_board(
    project_id: int,
    session: SessionDep,
    types: list[IssueType] = Query(default=[], alias="type"),
    assignee: str | None = Query(default=None),
    sprint: str | None = Query(default=None),
) -> BoardRead:
    assignee_id, unassigned = board_service.parse_assignee_filter(assignee)
    sprint_id, unscheduled = board_service.parse_sprint_filter(sprint)
    board = board_service.project_board(
        session,
        project_id,
        types,
        assignee_id=assignee_id,
        unassigned=unassigned,
        sprint_id=sprint_id,
        unscheduled=unscheduled,
    )
    return BoardRead(
        project_id=board.project.id,
        columns=[
            BoardColumnRead(
                status=column.status,
                label=label(column.status),
                issues=[
                    IssueRead.of(card.issue, board.project) for card in column.cards
                ],
            )
            for column in board.columns
        ],
    )


@router.get("/projects/{project_id}/backlog", response_model=list[IssueRead])
def read_backlog(project_id: int, session: SessionDep) -> list[IssueRead]:
    project = project_service.get_project(session, project_id)
    return [
        IssueRead.of(issue, project)
        for issue in backlog_service.project_backlog(session, project.id)
    ]
