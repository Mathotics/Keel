from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from keel.db.models import Issue, Project, Sprint
from keel.domain.enums import (
    IssueStatus,
    IssueType,
    SprintState,
    statuses_in_workflow_order,
)
from keel.domain.errors import InvalidIssueError
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.issues import IssueFilters


@dataclass(frozen=True)
class BoardCard:
    issue: Issue
    key: str
    assignee_name: str | None


@dataclass(frozen=True)
class BoardColumn:
    status: IssueStatus
    cards: tuple[BoardCard, ...]


@dataclass(frozen=True)
class BoardLane:
    sprint_id: int | None
    name: str
    state: SprintState | None
    columns: tuple[BoardColumn, ...]


@dataclass(frozen=True)
class Board:
    project: Project
    columns: tuple[BoardColumn, ...]
    lanes: tuple[BoardLane, ...]


def parse_assignee_filter(raw: str | None) -> tuple[int | None, bool]:
    """Read the board's `assignee` query value.

    Empty means every assignee. `unassigned` means no assignee. Otherwise a
    user identifier.
    """
    return _parse_id_filter(raw, none_token="unassigned", kind="assignee")


def parse_sprint_filter(raw: str | None) -> tuple[int | None, bool]:
    """Read the board's `sprint` query value.

    Empty means every sprint. `unscheduled` means no sprint. Otherwise a
    sprint identifier.
    """
    return _parse_id_filter(raw, none_token="unscheduled", kind="sprint")


def parse_board_grouping(raw: str | None) -> str | None:
    """Read the board's `by` query value.

    Empty means one shared set of columns. `sprint` stacks a row per sprint.
    """
    if raw is None or not raw.strip():
        return None
    cleaned = raw.strip()
    if cleaned == "sprint":
        return "sprint"
    raise InvalidIssueError(f"{cleaned} is not a valid board grouping.")


def _parse_id_filter(
    raw: str | None,
    *,
    none_token: str,
    kind: str,
) -> tuple[int | None, bool]:
    if raw is None or not raw.strip():
        return None, False
    cleaned = raw.strip()
    if cleaned == none_token:
        return None, True
    if cleaned.isdigit():
        return int(cleaned), False
    raise InvalidIssueError(f"{cleaned} is not a valid {kind} filter.")


def project_board(
    session: Session,
    project_id: int,
    types: Sequence[IssueType] = (),
    *,
    assignee_id: int | None = None,
    unassigned: bool = False,
    sprint_id: int | None = None,
    unscheduled: bool = False,
) -> Board:
    """Group a project's issues by status in workflow order.

    Type, assignee, and sprint filters are applied in the query so hidden
    cards are never loaded. Empty `types` means every type; omitting
    assignee or sprint means every value. That matches the board's default.
    Lanes always regroup the same cards by sprint so the page can stack a
    row per sprint without a second query.
    """
    project = project_service.get_project(session, project_id)
    found = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(
            types=tuple(types),
            assignee_id=assignee_id,
            unassigned=unassigned,
            sprint_id=sprint_id,
            unscheduled=unscheduled,
        ),
    )
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    cards = tuple(
        BoardCard(
            issue=issue,
            key=issue_service.issue_key(issue, project),
            assignee_name=(names.get(issue.assignee_id) if issue.assignee_id else None),
        )
        for issue in found
    )
    return Board(
        project=project,
        columns=_columns_from(cards),
        lanes=_lanes(
            cards,
            sprint_service.list_sprints(session, project.id),
            sprint_id=sprint_id,
            unscheduled=unscheduled,
        ),
    )


def _columns_from(cards: Sequence[BoardCard]) -> tuple[BoardColumn, ...]:
    grouped: dict[IssueStatus, list[BoardCard]] = {
        status: [] for status in statuses_in_workflow_order()
    }
    for card in cards:
        grouped[card.issue.status].append(card)
    return tuple(
        BoardColumn(status=status, cards=tuple(grouped[status]))
        for status in statuses_in_workflow_order()
    )


def _lanes(
    cards: Sequence[BoardCard],
    sprints: Sequence[Sprint],
    *,
    sprint_id: int | None,
    unscheduled: bool,
) -> tuple[BoardLane, ...]:
    by_sprint: dict[int | None, list[BoardCard]] = {}
    for card in cards:
        by_sprint.setdefault(card.issue.sprint_id, []).append(card)

    def lane_for(sprint: Sprint) -> BoardLane:
        return BoardLane(
            sprint_id=sprint.id,
            name=sprint.name,
            state=sprint.state,
            columns=_columns_from(by_sprint.get(sprint.id, ())),
        )

    unscheduled_lane = BoardLane(
        sprint_id=None,
        name="Unscheduled",
        state=None,
        columns=_columns_from(by_sprint.get(None, ())),
    )
    if unscheduled:
        return (unscheduled_lane,)
    if sprint_id is not None:
        chosen = [sprint for sprint in sprints if sprint.id == sprint_id]
        return tuple(lane_for(sprint) for sprint in chosen)

    lanes: list[BoardLane] = []
    for sprint in sprints:
        owned = by_sprint.get(sprint.id, ())
        if owned or sprint.state in (SprintState.PLANNED, SprintState.ACTIVE):
            lanes.append(lane_for(sprint))
    lanes.append(unscheduled_lane)
    return tuple(lanes)
