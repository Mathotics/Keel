from fastapi import APIRouter, Query, status
from sqlalchemy.orm import Session

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.db.models import Issue
from keel.domain.enums import IssueStatus, IssueType
from keel.schemas.issue import IssueCreate, IssueRead, IssueUpdate
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services.issues import IssueFilters

router = APIRouter(tags=["issues"])


def _read(session: Session, issue: Issue) -> IssueRead:
    return IssueRead.of(issue, project_service.get_project(session, issue.project_id))


@router.get("/projects/{project_id}/issues", response_model=list[IssueRead])
def list_issues(
    project_id: int,
    session: SessionDep,
    type: IssueType | None = Query(default=None),
    status_: IssueStatus | None = Query(default=None, alias="status"),
    assignee_id: int | None = Query(default=None),
    parent_id: int | None = Query(default=None),
) -> list[IssueRead]:
    project = project_service.get_project(session, project_id)
    found = issue_service.list_issues(
        session,
        project.id,
        IssueFilters(
            type=type,
            status=status_,
            assignee_id=assignee_id,
            parent_id=parent_id,
        ),
    )
    return [IssueRead.of(issue, project) for issue in found]


@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueRead,
    status_code=status.HTTP_201_CREATED,
)
def create_issue(
    project_id: int,
    payload: IssueCreate,
    session: SessionDep,
    acting_user: ActingUserDep,
) -> IssueRead:
    issue = issue_service.create_issue(
        session,
        project_id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        parent_id=payload.parent_id,
        reporter_id=None if acting_user is None else acting_user.id,
        assignee_id=payload.assignee_id,
    )
    return _read(session, issue)


@router.get("/issues/{issue_id}", response_model=IssueRead)
def read_issue(issue_id: int, session: SessionDep) -> IssueRead:
    return _read(session, issue_service.get_issue(session, issue_id))


@router.get("/issues/{issue_id}/children", response_model=list[IssueRead])
def read_children(issue_id: int, session: SessionDep) -> list[IssueRead]:
    issue = issue_service.get_issue(session, issue_id)
    project = project_service.get_project(session, issue.project_id)
    children = issue_service.list_children(session, issue.id)
    return [IssueRead.of(child, project) for child in children]


@router.patch("/issues/{issue_id}", response_model=IssueRead)
def update_issue(
    issue_id: int,
    payload: IssueUpdate,
    session: SessionDep,
) -> IssueRead:
    supplied = payload.model_fields_set
    issue = issue_service.update_issue(
        session,
        issue_id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        parent_id=payload.parent_id if "parent_id" in supplied else issue_service.UNSET,
        assignee_id=(
            payload.assignee_id if "assignee_id" in supplied else issue_service.UNSET
        ),
    )
    return _read(session, issue)


@router.delete("/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(issue_id: int, session: SessionDep) -> None:
    issue_service.delete_issue(session, issue_id)
