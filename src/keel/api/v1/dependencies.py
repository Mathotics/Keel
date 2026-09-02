from fastapi import APIRouter, status

from keel.api.v1.deps import SessionDep
from keel.schemas.dependency import (
    DependencyCreate,
    DependencyRead,
    IssueDependenciesRead,
    LinkedIssueRead,
)
from keel.services import dependencies as dependency_service
from keel.services.dependencies import DependencyLink, IssueDependencies

router = APIRouter(tags=["dependencies"])


def _linked(link: DependencyLink) -> LinkedIssueRead:
    return LinkedIssueRead(
        dependency_id=link.id,
        id=link.issue.id,
        key=link.key,
        title=link.issue.title,
        project_id=link.issue.project_id,
        project_key=link.project_key,
    )


def _groups(groups: IssueDependencies) -> IssueDependenciesRead:
    return IssueDependenciesRead(
        blocks=[_linked(link) for link in groups.blocks],
        blocked_by=[_linked(link) for link in groups.blocked_by],
        relates_to=[_linked(link) for link in groups.relates_to],
    )


@router.get(
    "/issues/{issue_id}/dependencies",
    response_model=IssueDependenciesRead,
)
def list_dependencies(issue_id: int, session: SessionDep) -> IssueDependenciesRead:
    return _groups(dependency_service.list_for_issue(session, issue_id))


@router.post(
    "/dependencies",
    response_model=DependencyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(payload: DependencyCreate, session: SessionDep) -> DependencyRead:
    return DependencyRead.of(
        dependency_service.create_dependency(
            session,
            payload.source_id,
            payload.target_id,
            payload.kind,
        ),
    )


@router.delete(
    "/dependencies/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dependency(dependency_id: int, session: SessionDep) -> None:
    dependency_service.delete_dependency(session, dependency_id)
