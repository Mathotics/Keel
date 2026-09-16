from enum import StrEnum


class IssueType(StrEnum):
    EPIC = "epic"
    STORY = "story"
    SUBTASK = "subtask"


class IssuePriority(StrEnum):
    """Declaration order is rank: P1 is highest, P5 is lowest."""

    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"
    P5 = "p5"


class IssueStatus(StrEnum):
    """Declaration order is the workflow order the board renders in."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class SprintState(StrEnum):
    """Declaration order is the only allowed lifecycle."""

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


class SprintCadence(StrEnum):
    """How often a project closes and opens sprints. Off is the default."""

    OFF = "off"
    WEEKLY = "weekly"
    TWO_WEEKS = "two_weeks"
    MONTHLY = "monthly"
    EVERY_N_DAYS = "every_n_days"


class SeriesState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class SeriesSpawnMode(StrEnum):
    CALENDAR = "calendar"
    AFTER_CLOSED = "after_closed"


class SeriesSprintBasis(StrEnum):
    DUE_ON = "due_on"
    CREATED_ON = "created_on"


class RecurrenceFreq(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class EditScope(StrEnum):
    THIS = "this"
    FUTURE = "future"
    SERIES = "series"


class DependencyKind(StrEnum):
    BLOCKS = "blocks"
    RELATES_TO = "relates_to"


INITIAL_STATUS = IssueStatus.TODO
INITIAL_PRIORITY = IssuePriority.P3
COMPLETED_STATUS = IssueStatus.DONE
CLOSED_STATUSES = frozenset({IssueStatus.DONE, IssueStatus.CANCELLED})

_LABELS = {
    IssueType.EPIC: "Epic",
    IssueType.STORY: "Story",
    IssueType.SUBTASK: "Subtask",
    IssuePriority.P1: "P1 — Blocker",
    IssuePriority.P2: "P2 — Critical",
    IssuePriority.P3: "P3 — Major",
    IssuePriority.P4: "P4 — Minor",
    IssuePriority.P5: "P5 — Trivial",
    IssueStatus.TODO: "To Do",
    IssueStatus.IN_PROGRESS: "In Progress",
    IssueStatus.IN_REVIEW: "In Review",
    IssueStatus.BLOCKED: "Blocked",
    IssueStatus.DONE: "Done",
    IssueStatus.CANCELLED: "Cancelled",
    SprintState.PLANNED: "Planned",
    SprintState.ACTIVE: "Active",
    SprintState.COMPLETED: "Completed",
    SprintCadence.OFF: "Off",
    SprintCadence.WEEKLY: "Weekly",
    SprintCadence.TWO_WEEKS: "Every 2 weeks",
    SprintCadence.MONTHLY: "Monthly",
    SprintCadence.EVERY_N_DAYS: "Every N days",
    DependencyKind.BLOCKS: "Blocks",
    DependencyKind.RELATES_TO: "Relates to",
    SeriesState.ACTIVE: "Active",
    SeriesState.PAUSED: "Paused",
    SeriesState.STOPPED: "Stopped",
    SeriesSpawnMode.CALENDAR: "On the calendar",
    SeriesSpawnMode.AFTER_CLOSED: "After the previous copy is closed",
    SeriesSprintBasis.DUE_ON: "Due date",
    SeriesSprintBasis.CREATED_ON: "Creation date",
    RecurrenceFreq.DAILY: "Daily",
    RecurrenceFreq.WEEKLY: "Weekly",
    RecurrenceFreq.MONTHLY: "Monthly",
    RecurrenceFreq.YEARLY: "Yearly",
    EditScope.THIS: "This occurrence",
    EditScope.FUTURE: "This and all future",
    EditScope.SERIES: "Entire series",
}

Labeled = (
    IssueType
    | IssuePriority
    | IssueStatus
    | SprintState
    | SprintCadence
    | DependencyKind
    | SeriesState
    | SeriesSpawnMode
    | SeriesSprintBasis
    | RecurrenceFreq
    | EditScope
)


def label(value: Labeled) -> str:
    return _LABELS[value]


def statuses_in_workflow_order() -> tuple[IssueStatus, ...]:
    return tuple(IssueStatus)


def types_in_hierarchy_order() -> tuple[IssueType, ...]:
    return tuple(IssueType)


def priorities_in_rank_order() -> tuple[IssuePriority, ...]:
    return tuple(IssuePriority)


def sprint_states_in_lifecycle_order() -> tuple[SprintState, ...]:
    return tuple(SprintState)


def sprint_cadences_in_menu_order() -> tuple[SprintCadence, ...]:
    return tuple(SprintCadence)
