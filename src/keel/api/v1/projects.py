from fastapi import APIRouter, status

from keel.api.v1.deps import SessionDep
from keel.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from keel.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(session: SessionDep) -> list[ProjectRead]:
    return [
        ProjectRead.model_validate(project)
        for project in project_service.list_projects(session)
    ]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: SessionDep) -> ProjectRead:
    project = project_service.create_project(
        session,
        payload.key,
        payload.name,
        payload.description,
    )
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead)
def read_project(project_id: int, session: SessionDep) -> ProjectRead:
    return ProjectRead.model_validate(project_service.get_project(session, project_id))


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    session: SessionDep,
) -> ProjectRead:
    supplied = payload.model_fields_set
    project = project_service.update_project(
        session,
        project_id,
        payload.name,
        payload.description,
        sprint_cadence=(
            payload.sprint_cadence
            if "sprint_cadence" in supplied
            else project_service.UNSET
        ),
        sprint_cadence_days=(
            payload.sprint_cadence_days
            if "sprint_cadence_days" in supplied
            else project_service.UNSET
        ),
        sprint_ahead=(
            payload.sprint_ahead
            if "sprint_ahead" in supplied
            else project_service.UNSET
        ),
    )
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, session: SessionDep) -> None:
    project_service.delete_project(session, project_id)
