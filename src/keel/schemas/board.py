from pydantic import BaseModel

from keel.domain.enums import IssueStatus, SprintState
from keel.schemas.issue import IssueRead


class BoardColumnRead(BaseModel):
    status: IssueStatus
    label: str
    issues: list[IssueRead]


class BoardLaneRead(BaseModel):
    sprint_id: int | None
    name: str
    state: SprintState | None
    columns: list[BoardColumnRead]


class BoardRead(BaseModel):
    project_id: int
    columns: list[BoardColumnRead]
    lanes: list[BoardLaneRead]
