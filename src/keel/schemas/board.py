from pydantic import BaseModel

from keel.domain.enums import IssueStatus
from keel.schemas.issue import IssueRead


class BoardColumnRead(BaseModel):
    status: IssueStatus
    label: str
    issues: list[IssueRead]


class BoardRead(BaseModel):
    project_id: int
    columns: list[BoardColumnRead]
