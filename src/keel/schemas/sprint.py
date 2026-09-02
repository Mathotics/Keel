from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from keel.db.models import Sprint
from keel.domain.enums import SprintState
from keel.schemas.issue import IssueRead


class SprintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = ""
    starts_on: date | None = None
    ends_on: date | None = None


class SprintUpdate(BaseModel):
    """Absent fields are left alone; an explicit null clears a date."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None


class SprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    goal: str
    state: SprintState
    starts_on: date | None
    ends_on: date | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def of(cls, sprint: Sprint) -> "SprintRead":
        return cls.model_validate(sprint)


class SprintDetailRead(SprintRead):
    issues: list[IssueRead]


class SprintStateRead(BaseModel):
    id: int
    state: SprintState


class SprintCompletionRead(BaseModel):
    sprint: SprintStateRead
    carried_over: int
    carried_to_sprint_id: int | None
