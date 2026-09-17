from collections.abc import Sequence

from fastapi import APIRouter, Query

from keel.api.v1.deps import SessionDep
from keel.domain.enums import IssueType, label
from keel.schemas.board import BoardColumnRead, BoardLaneRead, BoardRead
from keel.schemas.issue import IssueRead
from keel.services import backlog as backlog_service
from keel.services import boards as board_service
from keel.services import labels as label_service
from keel.services import projects as project_service
from keel.services.boards import Board, BoardColumn

router = APIRouter(tags=["boards"])


@router.get("/projects/{project_id}/board", response_model=BoardRead)
def read_board(
    project_id: int,
    session: SessionDep,
    types: list[IssueType] = Query(default=[], alias="type"),
    assignee: str | None = Query(default=None),
    sprint: str | None = Query(default=None),
    label: str | None = Query(default=None),
) -> BoardRead:
    assignee_id, unassigned = board_service.parse_assignee_filter(assignee)
    sprint_id, unscheduled = board_service.parse_sprint_filter(sprint)
    label_name, unlabeled = board_service.parse_label_filter(label)
    board = board_service.project_board(
        session,
        project_id,
        types,
        assignee_id=assignee_id,
        unassigned=unassigned,
        sprint_id=sprint_id,
        unscheduled=unscheduled,
        label=label_name,
        unlabeled=unlabeled,
    )
    return BoardRead(
        project_id=board.project.id,
        columns=_column_reads(board),
        lanes=[
            BoardLaneRead(
                sprint_id=lane.sprint_id,
                name=lane.name,
                state=lane.state,
                columns=_column_reads(board, lane.columns),
            )
            for lane in board.lanes
        ],
    )


def _column_reads(
    board: Board,
    columns: Sequence[BoardColumn] | None = None,
) -> list[BoardColumnRead]:
    chosen = board.columns if columns is None else columns
    return [
        BoardColumnRead(
            status=column.status,
            label=label(column.status),
            issues=[
                IssueRead.of(
                    card.issue,
                    board.project,
                    card.unresolved_blockers,
                    labels=card.labels,
                )
                for card in column.cards
            ],
        )
        for column in chosen
    ]


@router.get("/projects/{project_id}/backlog", response_model=list[IssueRead])
def read_backlog(project_id: int, session: SessionDep) -> list[IssueRead]:
    project = project_service.get_project(session, project_id)
    items = backlog_service.project_backlog(session, project.id)
    names = label_service.names_for_issues(
        session,
        [item.issue.id for item in items],
    )
    return [
        IssueRead.of(
            item.issue,
            project,
            item.unresolved_blockers,
            labels=names.get(item.issue.id, ()),
        )
        for item in items
    ]
