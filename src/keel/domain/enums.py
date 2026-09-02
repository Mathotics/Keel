from enum import StrEnum


class IssueType(StrEnum):
    EPIC = "epic"
    STORY = "story"
    SUBTASK = "subtask"


class IssueStatus(StrEnum):
    """Declaration order is the workflow order the board renders in."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"


class SprintState(StrEnum):
    """Declaration order is the only allowed lifecycle."""

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


INITIAL_STATUS = IssueStatus.TODO
TERMINAL_STATUS = IssueStatus.DONE

_LABELS = {
    IssueType.EPIC: "Epic",
    IssueType.STORY: "Story",
    IssueType.SUBTASK: "Subtask",
    IssueStatus.TODO: "To Do",
    IssueStatus.IN_PROGRESS: "In Progress",
    IssueStatus.IN_REVIEW: "In Review",
    IssueStatus.BLOCKED: "Blocked",
    IssueStatus.DONE: "Done",
    SprintState.PLANNED: "Planned",
    SprintState.ACTIVE: "Active",
    SprintState.COMPLETED: "Completed",
}

Labeled = IssueType | IssueStatus | SprintState


def label(value: Labeled) -> str:
    return _LABELS[value]


def statuses_in_workflow_order() -> tuple[IssueStatus, ...]:
    return tuple(IssueStatus)


def types_in_hierarchy_order() -> tuple[IssueType, ...]:
    return tuple(IssueType)


def sprint_states_in_lifecycle_order() -> tuple[SprintState, ...]:
    return tuple(SprintState)
