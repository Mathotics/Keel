from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from keel.db.models import Series
from keel.domain.enums import (
    INITIAL_PRIORITY,
    IssuePriority,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
)
from keel.services.series import cadence_summary


class SeriesCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    type: IssueType
    priority: IssuePriority = INITIAL_PRIORITY
    spawn_mode: SeriesSpawnMode
    sprint_basis: SeriesSprintBasis
    freq: RecurrenceFreq
    starts_on: date
    interval: int = Field(default=1, ge=1)
    weekdays: list[int] = Field(default_factory=list)
    month_day: int | None = Field(default=None, ge=1, le=31)
    nth_week: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    ends_on: date | None = None
    occurrence_count: int | None = Field(default=None, ge=1)
    look_ahead_n: int = Field(default=1, ge=1)
    start_offset_days: int = 0
    start_minute_of_day: int = Field(default=0, ge=0, lt=1440)
    due_offset_days: int = 0
    due_minute_of_day: int = Field(default=0, ge=0, lt=1440)
    parent_id: int | None = None
    assignee_id: int | None = None
    seed_issue_id: int | None = None


class SeriesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    type: IssueType | None = None
    priority: IssuePriority | None = None
    spawn_mode: SeriesSpawnMode | None = None
    sprint_basis: SeriesSprintBasis | None = None
    freq: RecurrenceFreq | None = None
    interval: int | None = Field(default=None, ge=1)
    weekdays: list[int] | None = None
    month_day: int | None = None
    nth_week: int | None = None
    month: int | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    occurrence_count: int | None = None
    look_ahead_n: int | None = Field(default=None, ge=1)
    start_offset_days: int | None = None
    start_minute_of_day: int | None = Field(default=None, ge=0, lt=1440)
    due_offset_days: int | None = None
    due_minute_of_day: int | None = Field(default=None, ge=0, lt=1440)
    parent_id: int | None = None
    assignee_id: int | None = None
    state: SeriesState | None = None


class SeriesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str
    type: IssueType
    priority: IssuePriority
    state: SeriesState
    spawn_mode: SeriesSpawnMode
    sprint_basis: SeriesSprintBasis
    look_ahead_n: int
    start_offset_days: int
    start_minute_of_day: int
    due_offset_days: int
    due_minute_of_day: int
    freq: RecurrenceFreq
    interval: int
    weekdays: str
    month_day: int | None
    nth_week: int | None
    month: int | None
    starts_on: date
    ends_on: date | None
    occurrence_count: int | None
    parent_id: int | None
    assignee_id: int | None
    reporter_id: int | None
    cadence_summary: str

    @classmethod
    def of(cls, series: Series) -> "SeriesRead":
        return cls(
            id=series.id,
            project_id=series.project_id,
            title=series.title,
            description=series.description,
            type=series.type,
            priority=series.priority,
            state=series.state,
            spawn_mode=series.spawn_mode,
            sprint_basis=series.sprint_basis,
            look_ahead_n=series.look_ahead_n,
            start_offset_days=series.start_offset_days,
            start_minute_of_day=series.start_minute_of_day,
            due_offset_days=series.due_offset_days,
            due_minute_of_day=series.due_minute_of_day,
            freq=series.freq,
            interval=series.interval,
            weekdays=series.weekdays,
            month_day=series.month_day,
            nth_week=series.nth_week,
            month=series.month,
            starts_on=series.starts_on,
            ends_on=series.ends_on,
            occurrence_count=series.occurrence_count,
            parent_id=series.parent_id,
            assignee_id=series.assignee_id,
            reporter_id=series.reporter_id,
            cadence_summary=cadence_summary(series),
        )
