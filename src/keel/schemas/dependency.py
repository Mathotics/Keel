from datetime import datetime

from pydantic import BaseModel, ConfigDict

from keel.db.models import Dependency
from keel.domain.enums import DependencyKind


class DependencyCreate(BaseModel):
    source_id: int
    target_id: int
    kind: DependencyKind


class DependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    target_id: int
    kind: DependencyKind
    created_at: datetime

    @classmethod
    def of(cls, dependency: Dependency) -> "DependencyRead":
        return cls.model_validate(dependency)


class LinkedIssueRead(BaseModel):
    dependency_id: int
    id: int
    key: str
    title: str
    project_id: int
    project_key: str


class IssueDependenciesRead(BaseModel):
    blocks: list[LinkedIssueRead]
    blocked_by: list[LinkedIssueRead]
    relates_to: list[LinkedIssueRead]
