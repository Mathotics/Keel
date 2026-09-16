from collections.abc import Mapping, Sequence
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from keel.db.models import Issue, Project
from keel.domain.enums import (
    INITIAL_PRIORITY,
    INITIAL_STATUS,
    IssuePriority,
    IssueStatus,
    IssueType,
)
from keel.domain.rollup import Rollup


class IssueCreate(BaseModel):
    type: IssueType
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    status: IssueStatus = INITIAL_STATUS
    priority: IssuePriority = INITIAL_PRIORITY
    parent_id: int | None = None
    sprint_id: int | None = None
    assignee_id: int | None = None
    estimate_minutes: int | None = Field(default=None, ge=0)
    remaining_minutes: int | None = Field(default=None, ge=0)
    due_at: datetime | None = None


class IssueUpdate(BaseModel):
    """Absent fields are left alone; an explicit null clears a nullable one.

    Callers read `model_fields_set` to tell those two cases apart.
    """

    model_config = ConfigDict(extra="forbid")

    type: IssueType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    parent_id: int | None = None
    sprint_id: int | None = None
    assignee_id: int | None = None
    estimate_minutes: int | None = Field(default=None, ge=0)
    remaining_minutes: int | None = Field(default=None, ge=0)
    due_at: datetime | None = None


class RollupRead(BaseModel):
    estimate_minutes: int | None
    remaining_minutes: int | None
    descendants: int
    descendants_done: int
    descendants_cancelled: int

    @classmethod
    def of(cls, rollup: Rollup) -> "RollupRead":
        return cls(
            estimate_minutes=rollup.estimate_minutes,
            remaining_minutes=rollup.remaining_minutes,
            descendants=rollup.descendants,
            descendants_done=rollup.descendants_done,
            descendants_cancelled=rollup.descendants_cancelled,
        )


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    project_id: int
    number: int
    type: IssueType
    title: str
    description: str
    status: IssueStatus
    priority: IssuePriority
    parent_id: int | None
    sprint_id: int | None
    reporter_id: int | None
    assignee_id: int | None
    estimate_minutes: int | None
    remaining_minutes: int | None
    due_at: datetime | None
    series_id: int | None = None
    occurrence_on: date | None = None
    unresolved_blockers: int
    rollup: RollupRead | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(
        cls,
        issue: Issue,
        project: Project,
        unresolved_blockers: int = 0,
        rollup: Rollup | None = None,
    ) -> "IssueRead":
        return cls(
            id=issue.id,
            key=f"{project.key}-{issue.number}",
            project_id=issue.project_id,
            number=issue.number,
            type=issue.type,
            title=issue.title,
            description=issue.description,
            status=issue.status,
            priority=issue.priority,
            parent_id=issue.parent_id,
            sprint_id=issue.sprint_id,
            reporter_id=issue.reporter_id,
            assignee_id=issue.assignee_id,
            estimate_minutes=issue.estimate_minutes,
            remaining_minutes=issue.remaining_minutes,
            due_at=issue.due_at,
            series_id=issue.series_id,
            occurrence_on=issue.occurrence_on,
            unresolved_blockers=unresolved_blockers,
            rollup=None if rollup is None else RollupRead.of(rollup),
            created_at=issue.created_at,
            updated_at=issue.updated_at,
        )

    @classmethod
    def many(
        cls,
        issues: Sequence[Issue],
        project: Project,
        blocker_counts: Mapping[int, int],
    ) -> list["IssueRead"]:
        return [
            cls.of(issue, project, blocker_counts.get(issue.id, 0)) for issue in issues
        ]
