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
    project: Project | None
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


def parse_project_filter(raw: str | None) -> str | None:
    """Read the master board's `project` query value.

    Empty means every project. Otherwise a project key.
    """
    if raw is None or not raw.strip():
        return None
    return raw.strip()


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


def card_count(board: Board) -> int:
    return sum(len(column.cards) for column in board.columns)


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
    return _board_from_issues(
        session,
        found,
        project=project,
        sprints=sprint_service.list_sprints(session, project.id),
        sprint_id=sprint_id,
        unscheduled=unscheduled,
    )


def master_board(
    session: Session,
    types: Sequence[IssueType] = (),
    *,
    project_id: int | None = None,
    assignee_id: int | None = None,
    unassigned: bool = False,
    sprint_id: int | None = None,
    unscheduled: bool = False,
    label: str | None = None,
    unlabeled: bool = False,
) -> Board:
    """Group issues from every project, omitting closed completed-sprint work."""
    found = issue_service.list_issues(
        session,
        project_id,
        IssueFilters(
            types=tuple(types),
            assignee_id=assignee_id,
            unassigned=unassigned,
            sprint_id=sprint_id,
            unscheduled=unscheduled,
            label=label,
            unlabeled=unlabeled,
            hide_closed_in_completed_sprints=True,
        ),
    )
    if project_id is not None:
        sprints = sprint_service.list_sprints(session, project_id)
        projects = {project_id: project_service.get_project(session, project_id)}
    else:
        sprints = sprint_service.list_all_sprints(session)
        projects = {item.id: item for item in project_service.list_projects(session)}
    return _board_from_issues(
        session,
        found,
        project=None,
        sprints=sprints,
        sprint_id=sprint_id,
        unscheduled=unscheduled,
        projects=projects,
        prefix_project=True,
    )


def _board_from_issues(
    session: Session,
    found: Sequence[Issue],
    *,
    project: Project | None,
    sprints: Sequence[Sprint],
    sprint_id: int | None,
    unscheduled: bool,
    projects: dict[int, Project] | None = None,
    prefix_project: bool = False,
) -> Board:
    by_id = projects or ({project.id: project} if project is not None else {})
    names = {user.id: user.display_name for user in user_service.list_users(session)}
    counts = dependency_service.unresolved_blocker_counts(
        session,
        [issue.id for issue in found],
    )
    parent_keys = _parent_keys(session, found, by_id)
    label_names = label_service.names_for_issues(
        session,
        [issue.id for issue in found],
    )
    cards = tuple(
        BoardCard(
            issue=issue,
            key=issue_service.issue_key(issue, by_id[issue.project_id]),
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
            sprints,
            sprint_id=sprint_id,
            unscheduled=unscheduled,
            projects=by_id,
            prefix_project=prefix_project,
        ),
    )


def _parent_keys(
    session: Session,
    issues: Sequence[Issue],
    projects: dict[int, Project],
) -> dict[int, str]:
    parent_ids = {issue.parent_id for issue in issues if issue.parent_id is not None}
    if not parent_ids:
        return {}
    parents = session.scalars(select(Issue).where(Issue.id.in_(parent_ids))).all()
    missing = {
        parent.project_id for parent in parents if parent.project_id not in projects
    }
    if missing:
        extra = session.scalars(select(Project).where(Project.id.in_(missing))).all()
        projects = {**projects, **{item.id: item for item in extra}}
    return {
        parent.id: issue_service.issue_key(parent, projects[parent.project_id])
        for parent in parents
    }


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
    projects: dict[int, Project] | None = None,
    prefix_project: bool = False,
) -> tuple[BoardLane, ...]:
    by_sprint: dict[int | None, list[BoardCard]] = {}
    for card in cards:
        by_sprint.setdefault(card.issue.sprint_id, []).append(card)

    def lane_name(sprint: Sprint) -> str:
        if prefix_project and projects is not None:
            return f"{projects[sprint.project_id].key} / {sprint.name}"
        return sprint.name

    def lane_for(sprint: Sprint) -> BoardLane:
        return BoardLane(
            sprint_id=sprint.id,
            name=lane_name(sprint),
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
