from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from keel.db.models import Issue, Project
from keel.domain.enums import INITIAL_STATUS, IssueStatus, IssueType


class IssueCreate(BaseModel):
    type: IssueType
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    status: IssueStatus = INITIAL_STATUS
    parent_id: int | None = None
    sprint_id: int | None = None
    assignee_id: int | None = None
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
    parent_id: int | None = None
    sprint_id: int | None = None
    assignee_id: int | None = None
    due_at: datetime | None = None


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
    parent_id: int | None
    sprint_id: int | None
    reporter_id: int | None
    assignee_id: int | None
    estimate_minutes: int | None
    remaining_minutes: int | None
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, issue: Issue, project: Project) -> "IssueRead":
        return cls(
            id=issue.id,
            key=f"{project.key}-{issue.number}",
            project_id=issue.project_id,
            number=issue.number,
            type=issue.type,
            title=issue.title,
            description=issue.description,
            status=issue.status,
            parent_id=issue.parent_id,
            sprint_id=issue.sprint_id,
            reporter_id=issue.reporter_id,
            assignee_id=issue.assignee_id,
            estimate_minutes=issue.estimate_minutes,
            remaining_minutes=issue.remaining_minutes,
            due_at=issue.due_at,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
        )
