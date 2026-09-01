from fastapi import APIRouter, Query

from keel.api.v1.deps import SessionDep
from keel.domain.enums import IssueType, label
from keel.schemas.board import BoardColumnRead, BoardRead
from keel.schemas.issue import IssueRead
from keel.services import boards as board_service

router = APIRouter(tags=["boards"])


@router.get("/projects/{project_id}/board", response_model=BoardRead)
def read_board(
    project_id: int,
    session: SessionDep,
    types: list[IssueType] = Query(default=[], alias="type"),
) -> BoardRead:
    board = board_service.project_board(session, project_id, types)
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
