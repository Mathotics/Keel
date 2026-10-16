from pydantic import BaseModel

from keel.domain.enums import IssueType


class FindIssueHitRead(BaseModel):
    id: int
    key: str
    title: str
    type: IssueType
    project_key: str
    snippet: str | None


class FindProjectHitRead(BaseModel):
    id: int
    key: str
    name: str
    snippet: str | None


class FindSprintHitRead(BaseModel):
    id: int
    name: str
    project_id: int
    project_key: str
    snippet: str | None


class FindUserHitRead(BaseModel):
    display_name: str


class FindJumpRead(BaseModel):
    kind: str = "jump"
    target: str
    url: str
    issue_id: int | None = None
    project_id: int | None = None
    project_key: str | None = None
    sprint_id: int | None = None
    key: str | None = None
    display_name: str | None = None


class FindResultsRead(BaseModel):
    kind: str = "results"
    query: str
    issues: list[FindIssueHitRead]
    issues_more: bool
    projects: list[FindProjectHitRead]
    projects_more: bool
    sprints: list[FindSprintHitRead]
    sprints_more: bool
    users: list[FindUserHitRead]
    users_more: bool
    empty: bool
