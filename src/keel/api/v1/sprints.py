from fastapi import APIRouter, Query, status
from sqlalchemy.orm import Session

from keel.api.v1.deps import SessionDep
from keel.db.models import Sprint
from keel.domain.enums import SprintState
from keel.schemas.issue import IssueRead
from keel.schemas.sprint import (
    SprintCompletionRead,
    SprintCreate,
    SprintDetailRead,
    SprintRead,
    SprintStateRead,
    SprintUpdate,
)
from keel.services import auto_sprint
from keel.services import dependencies as dependency_service
from keel.services import projects as project_service
from keel.services import sprints as sprint_service

router = APIRouter(tags=["sprints"])


def _detail(session: Session, sprint: Sprint) -> SprintDetailRead:
    project = project_service.get_project(session, sprint.project_id)
    issues = sprint_service.list_sprint_issues(session, sprint.id)
    counts = dependency_service.unresolved_blocker_counts(
        session,
        [issue.id for issue in issues],
    )
    return SprintDetailRead(
        **SprintRead.of(sprint).model_dump(),
        issues=IssueRead.many(issues, project, counts),
    )


@router.get("/projects/{project_id}/sprints", response_model=list[SprintRead])
def list_sprints(
    project_id: int,
    session: SessionDep,
    state: SprintState | None = Query(default=None),
) -> list[SprintRead]:
    return [
        SprintRead.of(sprint)
        for sprint in sprint_service.list_sprints(session, project_id, state)
    ]


@router.post(
    "/projects/{project_id}/sprints",
    response_model=SprintRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sprint(
    project_id: int,
    payload: SprintCreate,
    session: SessionDep,
) -> SprintRead:
    sprint = sprint_service.create_sprint(
        session,
        project_id,
        name=payload.name,
        goal=payload.goal,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
    )
    return SprintRead.of(sprint)


@router.get("/sprints/{sprint_id}", response_model=SprintDetailRead)
def read_sprint(sprint_id: int, session: SessionDep) -> SprintDetailRead:
    return _detail(session, sprint_service.get_sprint(session, sprint_id))


@router.patch("/sprints/{sprint_id}", response_model=SprintRead)
def update_sprint(
    sprint_id: int,
    payload: SprintUpdate,
    session: SessionDep,
) -> SprintRead:
    supplied = payload.model_fields_set
    sprint = sprint_service.update_sprint(
        session,
        sprint_id,
        name=payload.name,
        goal=payload.goal,
        starts_on=(
            payload.starts_on if "starts_on" in supplied else sprint_service.UNSET
        ),
        ends_on=payload.ends_on if "ends_on" in supplied else sprint_service.UNSET,
    )
    return SprintRead.of(sprint)


@router.delete("/sprints/{sprint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sprint(sprint_id: int, session: SessionDep) -> None:
    auto_sprint.delete_sprint(session, sprint_id)


@router.post("/sprints/{sprint_id}/start", response_model=SprintRead)
def start_sprint(sprint_id: int, session: SessionDep) -> SprintRead:
    return SprintRead.of(auto_sprint.start_sprint(session, sprint_id))


@router.post("/sprints/{sprint_id}/complete", response_model=SprintCompletionRead)
def complete_sprint(sprint_id: int, session: SessionDep) -> SprintCompletionRead:
    result = auto_sprint.complete_sprint(session, sprint_id)
    return SprintCompletionRead(
        sprint=SprintStateRead(id=result.sprint.id, state=result.sprint.state),
        carried_over=result.carried_over,
        carried_to_sprint_id=result.carried_to_sprint_id,
    )
