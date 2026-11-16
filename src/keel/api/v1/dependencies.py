from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from keel.api.v1.deps import SessionDep
from keel.api.v1.guards import (
    AccessDep,
    require_dependency_delete,
    require_issue,
)
from keel.domain.access import Permission
from keel.schemas.dependency import (
    DependencyCreate,
    DependencyRead,
    IssueDependenciesRead,
    LinkedIssueRead,
)
from keel.services import access as access_service
from keel.services import dependencies as dependency_service
from keel.services.access import Access
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


def _visible(
    session: SessionDep,
    access: Access,
    issue_id: int,
) -> IssueDependencies:
    groups = dependency_service.list_for_issue(session, issue_id)

    def keep(link: DependencyLink) -> bool:
        return access_service.holds_project(
            session,
            access,
            link.issue.project_id,
            Permission.VIEW_ISSUES,
        )

    return IssueDependencies(
        blocks=tuple(link for link in groups.blocks if keep(link)),
        blocked_by=tuple(link for link in groups.blocked_by if keep(link)),
        relates_to=tuple(link for link in groups.relates_to if keep(link)),
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
    dependencies=[Depends(require_issue(Permission.VIEW_ISSUES))],
)
def list_dependencies(
    issue_id: int,
    session: SessionDep,
    access: AccessDep,
) -> IssueDependenciesRead:
    return _groups(_visible(session, access, issue_id))


@router.get("/dependencies", response_model=list[DependencyRead])
def list_dependency_edges(
    session: SessionDep,
    access: AccessDep,
    issue_id: Annotated[list[int] | None, Query()] = None,
) -> list[DependencyRead]:
    for chosen in issue_id or ():
        access_service.require_project(
            session,
            access,
            access_service.project_of_issue(session, chosen),
            Permission.VIEW_ISSUES,
        )
    return [
        DependencyRead.of(row)
        for row in dependency_service.edges_among(session, issue_id or ())
    ]


@router.post(
    "/dependencies",
    response_model=DependencyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(
    payload: DependencyCreate,
    session: SessionDep,
    access: AccessDep,
) -> DependencyRead:
    access_service.require_dependency_projects(
        session,
        access,
        access_service.project_of_issue(session, payload.source_id),
        access_service.project_of_issue(session, payload.target_id),
    )
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
    dependencies=[Depends(require_dependency_delete)],
)
def delete_dependency(dependency_id: int, session: SessionDep) -> None:
    dependency_service.delete_dependency(session, dependency_id)
