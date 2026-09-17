from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project, Sprint
from keel.domain.enums import (
    IssueStatus,
    IssueType,
    SprintState,
    statuses_in_workflow_order,
)
from keel.domain.errors import InvalidIssueError
from keel.domain.labels import normalize_label_name
from keel.services import dependencies as dependency_service
from keel.services import issues as issue_service
from keel.services import labels as label_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service
from keel.services import users as user_service
from keel.services.issues import IssueFilters


@dataclass(frozen=True)
class BoardCard:
    issue: Issue
    key: str
    assignee_name: str | None
    unresolved_blockers: int
    parent_key: str | None = None
    labels: tuple[str, ...] = ()


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


def parse_label_filter(raw: str | None) -> tuple[str | None, bool]:
    """Read the board's `label` query value.

    Empty means every issue. `unlabeled` means no labels. Otherwise a
    normalized label name.
    """
    if raw is None or not raw.strip():
        return None, False
    cleaned = raw.strip()
    if cleaned == "unlabeled":
        return None, True
    return normalize_label_name(cleaned), False


def parse_board_grouping(raw: str | Sequence[str] | None) -> str | None:
    """Read the board's `by` query value.

    Missing means stacked by sprint. `sprint` stacks a row per sprint.
    `status` keeps one shared set of columns. Repeated values treat
    `sprint` as winning so a checked box can sit after a hidden `status`.
    """
    if raw is None:
        tokens: tuple[str, ...] = ()
    elif isinstance(raw, str):
        tokens = (raw,)
    else:
        tokens = tuple(raw)
    cleaned = tuple(item.strip() for item in tokens if item.strip())
    if not cleaned or "sprint" in cleaned:
        return "sprint"
    if all(item == "status" for item in cleaned):
        return None
    raise InvalidIssueError(f"{cleaned[-1]} is not a valid board grouping.")


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
    label: str | None = None,
    unlabeled: bool = False,
) -> Board:
    """Group a project's issues by status in workflow order.

    Type, assignee, sprint, and label filters are applied in the query so
    hidden cards are never loaded. Empty `types` means every type; omitting
    assignee, sprint, or label means every value. That matches the board's
    default.
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
            label=label,
            unlabeled=unlabeled,
        ),
    )
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    counts = dependency_service.unresolved_blocker_counts(
        session,
        [issue.id for issue in found],
    )
    parent_keys = _parent_keys(session, project, found)
    label_names = label_service.names_for_issues(
        session,
        [issue.id for issue in found],
    )
    cards = tuple(
        BoardCard(
            issue=issue,
            key=issue_service.issue_key(issue, project),
            assignee_name=(names.get(issue.assignee_id) if issue.assignee_id else None),
            unresolved_blockers=counts.get(issue.id, 0),
            parent_key=parent_keys.get(issue.parent_id) if issue.parent_id else None,
            labels=tuple(label_names.get(issue.id, ())),
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


def _parent_keys(
    session: Session,
    project: Project,
    issues: Sequence[Issue],
) -> dict[int, str]:
    parent_ids = {issue.parent_id for issue in issues if issue.parent_id is not None}
    if not parent_ids:
        return {}
    parents = session.scalars(select(Issue).where(Issue.id.in_(parent_ids))).all()
    return {parent.id: issue_service.issue_key(parent, project) for parent in parents}


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
