from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from keel.api.v1.deps import SessionDep
from keel.api.v1.guards import AccessDep
from keel.domain.access import Permission
from keel.domain.errors import NotFoundError
from keel.schemas.find import (
    FindIssueHitRead,
    FindJumpRead,
    FindProjectHitRead,
    FindResultsRead,
    FindSprintHitRead,
    FindUserHitRead,
)
from keel.services import access as access_service
from keel.services import find as find_service
from keel.services import projects as project_service

router = APIRouter(tags=["find"])


@router.get("/search", response_model=FindJumpRead | FindResultsRead)
def read_search(
    session: SessionDep,
    access: AccessDep,
    q: str = "",
    project: str | None = Query(default=None),
) -> FindJumpRead | FindResultsRead:
    allowed = access_service.project_ids_holding(
        session, access, Permission.VIEW_ISSUES
    )
    project_id = _project_id(session, project)
    if project_id is not None and allowed is not None and project_id not in allowed:
        project_id = None
    outcome = find_service.find(session, q, project_id, allowed=allowed)
    if isinstance(outcome, find_service.FindJump):
        return FindJumpRead(
            target=outcome.target,
            url=outcome.url,
            issue_id=outcome.issue_id,
            project_id=outcome.project_id,
            project_key=outcome.project_key,
            sprint_id=outcome.sprint_id,
            key=outcome.key,
            display_name=outcome.display_name,
        )
    return FindResultsRead(
        query=outcome.query,
        issues=[
            FindIssueHitRead.model_validate(hit, from_attributes=True)
            for hit in outcome.issues
        ],
        issues_more=outcome.issues_more,
        projects=[
            FindProjectHitRead.model_validate(hit, from_attributes=True)
            for hit in outcome.projects
        ],
        projects_more=outcome.projects_more,
        sprints=[
            FindSprintHitRead.model_validate(hit, from_attributes=True)
            for hit in outcome.sprints
        ],
        sprints_more=outcome.sprints_more,
        users=[
            FindUserHitRead.model_validate(hit, from_attributes=True)
            for hit in outcome.users
        ],
        users_more=outcome.users_more,
        empty=outcome.empty,
    )


def _project_id(session: Session, key: str | None) -> int | None:
    if not key:
        return None
    try:
        return project_service.get_project_by_key(session, key).id
    except NotFoundError:
        return None
