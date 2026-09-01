import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Board, Project
from keel.domain.errors import (
    DuplicateProjectKeyError,
    InvalidProjectKeyError,
    InvalidProjectNameError,
    NotFoundError,
)

KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
MAX_NAME_LENGTH = 200


def list_projects(session: Session) -> Sequence[Project]:
    return session.scalars(select(Project).order_by(Project.key)).all()


def get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"No project with id {project_id}.")
    return project


def get_project_by_key(session: Session, key: str) -> Project:
    project = session.scalars(
        select(Project).where(Project.key == key.upper()),
    ).first()
    if project is None:
        raise NotFoundError(f"No project with key {key}.")
    return project


def create_project(
    session: Session,
    key: str,
    name: str,
    description: str = "",
) -> Project:
    """Creates the project and its one board together, per ADR 013."""
    clean_key = _clean_key(key)
    _reject_duplicate_key(session, clean_key)
    project = Project(
        key=clean_key,
        name=_clean_name(name),
        description=description.strip(),
    )
    session.add(project)
    session.flush()
    session.add(Board(project_id=project.id, name=f"{project.key} board"))
    session.flush()
    return project


def update_project(
    session: Session,
    project_id: int,
    name: str | None = None,
    description: str | None = None,
) -> Project:
    """The key is immutable once issues carry it, so it is not updatable."""
    project = get_project(session, project_id)
    if name is not None:
        project.name = _clean_name(name)
    if description is not None:
        project.description = description.strip()
    session.flush()
    return project


def delete_project(session: Session, project_id: int) -> None:
    session.delete(get_project(session, project_id))
    session.flush()


def next_issue_number(session: Session, project: Project) -> int:
    """Draws from the project counter, which never goes backwards."""
    project.issue_seq += 1
    session.flush()
    return project.issue_seq


def _clean_key(key: str) -> str:
    candidate = key.strip().upper()
    if not KEY_PATTERN.fullmatch(candidate):
        raise InvalidProjectKeyError(
            "A project key is 2 to 10 characters, starts with a letter, "
            "and uses only letters and digits.",
            key=key,
        )
    return candidate


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidProjectNameError("A project needs a name.")
    return cleaned[:MAX_NAME_LENGTH]


def _reject_duplicate_key(session: Session, key: str) -> None:
    taken = session.scalars(select(Project).where(Project.key == key)).first()
    if taken is not None:
        raise DuplicateProjectKeyError(f"Project key {key} is already taken.", key=key)
