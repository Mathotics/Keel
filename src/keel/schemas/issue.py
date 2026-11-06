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
    definition_of_done: str = ""
    location: str = Field(default="", max_length=300)
    status: IssueStatus = INITIAL_STATUS
    priority: IssuePriority = INITIAL_PRIORITY
    parent_id: int | None = None
    sprint_id: int | None = None
    assignee_id: int | None = None
    estimate_minutes: int | None = Field(default=None, ge=0)
    remaining_minutes: int | None = Field(default=None, ge=0)
    planned_value_cents: int | None = Field(default=None, ge=0)
    earned_value_cents: int | None = Field(default=None, ge=0)
    actual_cost_cents: int | None = Field(default=None, ge=0)
    start_at: datetime | None = None
    due_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    client_key: str | None = None


class IssueUpdate(BaseModel):
    """Absent fields are left alone; an explicit null clears a nullable one.

    Callers read `model_fields_set` to tell those two cases apart.
    """

    model_config = ConfigDict(extra="forbid")

    type: IssueType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    definition_of_done: str | None = None
    location: str | None = Field(default=None, max_length=300)
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    parent_id: int | None = None
    sprint_id: int | None = None
    assignee_id: int | None = None
    estimate_minutes: int | None = Field(default=None, ge=0)
    remaining_minutes: int | None = Field(default=None, ge=0)
    planned_value_cents: int | None = Field(default=None, ge=0)
    earned_value_cents: int | None = Field(default=None, ge=0)
    actual_cost_cents: int | None = Field(default=None, ge=0)
    start_at: datetime | None = None
    due_at: datetime | None = None
    labels: list[str] | None = None


class RollupRead(BaseModel):
    estimate_minutes: int | None
    remaining_minutes: int | None
    descendants: int
    descendants_done: int
    descendants_cancelled: int
    planned_value_cents: int | None
    earned_value_cents: int | None
    actual_cost_cents: int | None
    budget_at_completion_cents: int | None
    estimate_at_completion_cents: int | None
    schedule_performance_index: float | None
    cost_performance_index: float | None

    @classmethod
    def of(cls, rollup: Rollup) -> "RollupRead":
        return cls(
            estimate_minutes=rollup.estimate_minutes,
            remaining_minutes=rollup.remaining_minutes,
            descendants=rollup.descendants,
            descendants_done=rollup.descendants_done,
            descendants_cancelled=rollup.descendants_cancelled,
            planned_value_cents=rollup.planned_value_cents,
            earned_value_cents=rollup.earned_value_cents,
            actual_cost_cents=rollup.actual_cost_cents,
            budget_at_completion_cents=rollup.budget_at_completion_cents,
            estimate_at_completion_cents=rollup.estimate_at_completion_cents,
            schedule_performance_index=rollup.schedule_performance_index,
            cost_performance_index=rollup.cost_performance_index,
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
    definition_of_done: str
    location: str
    status: IssueStatus
    priority: IssuePriority
    parent_id: int | None
    sprint_id: int | None
    reporter_id: int | None
    assignee_id: int | None
    estimate_minutes: int | None
    remaining_minutes: int | None
    planned_value_cents: int | None
    earned_value_cents: int | None
    actual_cost_cents: int | None
    start_at: datetime | None
    due_at: datetime | None
    series_id: int | None = None
    series_item_id: int | None = None
    series_item_title: str | None = None
    occurrence_on: date | None = None
    former_series_title: str | None = None
    former_series_cadence: str | None = None
    unresolved_blockers: int
    rollup: RollupRead | None = None
    labels: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(
        cls,
        issue: Issue,
        project: Project,
        unresolved_blockers: int = 0,
        rollup: Rollup | None = None,
        labels: Sequence[str] = (),
        series_item_title: str | None = None,
    ) -> "IssueRead":
        return cls(
            id=issue.id,
            key=f"{project.key}-{issue.number}",
            project_id=issue.project_id,
            number=issue.number,
            type=issue.type,
            title=issue.title,
            description=issue.description,
            definition_of_done=issue.definition_of_done,
            location=issue.location,
            status=issue.status,
            priority=issue.priority,
            parent_id=issue.parent_id,
            sprint_id=issue.sprint_id,
            reporter_id=issue.reporter_id,
            assignee_id=issue.assignee_id,
            estimate_minutes=issue.estimate_minutes,
            remaining_minutes=issue.remaining_minutes,
            planned_value_cents=issue.planned_value_cents,
            earned_value_cents=issue.earned_value_cents,
            actual_cost_cents=issue.actual_cost_cents,
            start_at=issue.start_at,
            due_at=issue.due_at,
            series_id=issue.series_id,
            series_item_id=issue.series_item_id,
            series_item_title=series_item_title,
            occurrence_on=issue.occurrence_on,
            former_series_title=issue.former_series_title,
            former_series_cadence=issue.former_series_cadence,
            unresolved_blockers=unresolved_blockers,
            rollup=None if rollup is None else RollupRead.of(rollup),
            labels=list(labels),
            created_at=issue.created_at,
            updated_at=issue.updated_at,
        )

    @classmethod
    def many(
        cls,
        issues: Sequence[Issue],
        project: Project,
        blocker_counts: Mapping[int, int],
        labels: Mapping[int, Sequence[str]] | None = None,
        series_item_titles: Mapping[int, str] | None = None,
    ) -> list["IssueRead"]:
        names = labels or {}
        titles = series_item_titles or {}
        return [
            cls.of(
                issue,
                project,
                blocker_counts.get(issue.id, 0),
                labels=names.get(issue.id, ()),
                series_item_title=(
                    None
                    if issue.series_item_id is None
                    else titles.get(issue.series_item_id)
                ),
            )
            for issue in issues
        ]
