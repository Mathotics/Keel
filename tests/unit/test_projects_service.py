import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Board
from keel.domain.errors import (
    DuplicateProjectKeyError,
    InvalidProjectKeyError,
    InvalidProjectNameError,
    NotFoundError,
)
from keel.services import projects as project_service


def test_creating_a_project_creates_its_board(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")

    board = session.scalars(
        select(Board).where(Board.project_id == project.id),
    ).one()
    assert board.name == "KEEL board"


def test_a_key_is_stored_uppercase(session: Session) -> None:
    project = project_service.create_project(session, " keel ", "Keel")
    assert project.key == "KEEL"


@pytest.mark.parametrize("key", ["K", "1KEEL", "KEEL-X", "TOOLONGAKEY", "", "KE EL"])
def test_malformed_keys_are_refused(session: Session, key: str) -> None:
    with pytest.raises(InvalidProjectKeyError) as caught:
        project_service.create_project(session, key, "Keel")
    assert caught.value.code == "project.invalid_key"
    assert caught.value.status_code == 422


def test_a_duplicate_key_is_refused(session: Session) -> None:
    project_service.create_project(session, "KEEL", "Keel")
    with pytest.raises(DuplicateProjectKeyError) as caught:
        project_service.create_project(session, "keel", "Other")
    assert caught.value.code == "project.duplicate_key"


def test_a_blank_name_is_refused(session: Session) -> None:
    with pytest.raises(InvalidProjectNameError):
        project_service.create_project(session, "KEEL", "   ")


def test_a_project_is_found_by_key_case_insensitively(session: Session) -> None:
    project_service.create_project(session, "KEEL", "Keel")
    assert project_service.get_project_by_key(session, "keel").name == "Keel"


def test_an_unknown_key_is_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        project_service.get_project_by_key(session, "NOPE")


def test_renaming_leaves_the_key_alone(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    updated = project_service.update_project(session, project.id, name="Keel Tracker")
    assert (updated.key, updated.name) == ("KEEL", "Keel Tracker")


def test_the_issue_counter_never_repeats(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    drawn = [project_service.next_issue_number(session, project) for _ in range(3)]
    assert drawn == [1, 2, 3]
