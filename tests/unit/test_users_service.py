import pytest
from sqlalchemy.orm import Session

from keel.domain.errors import (
    DuplicateUserNameError,
    InvalidUserNameError,
    NotFoundError,
)
from keel.services import users as user_service


def test_create_and_list_users(session: Session) -> None:
    user_service.create_user(session, "Ada")
    user_service.create_user(session, "Grace")
    assert [user.display_name for user in user_service.list_users(session)] == [
        "Ada",
        "Grace",
    ]


def test_create_user_trims_whitespace(session: Session) -> None:
    user = user_service.create_user(session, "  Ada  ")
    assert user.display_name == "Ada"


def test_create_user_rejects_a_blank_name(session: Session) -> None:
    with pytest.raises(InvalidUserNameError) as excinfo:
        user_service.create_user(session, "   ")
    assert excinfo.value.code == "user.invalid_name"
    assert excinfo.value.status_code == 422


def test_create_user_rejects_an_overlong_name(session: Session) -> None:
    with pytest.raises(InvalidUserNameError):
        user_service.create_user(session, "x" * 101)


def test_create_user_rejects_a_duplicate(session: Session) -> None:
    user_service.create_user(session, "Ada")
    with pytest.raises(DuplicateUserNameError) as excinfo:
        user_service.create_user(session, "Ada")
    assert excinfo.value.code == "user.duplicate_name"
    assert excinfo.value.context == {"display_name": "Ada"}


def test_get_user_raises_for_a_missing_id(session: Session) -> None:
    with pytest.raises(NotFoundError):
        user_service.get_user(session, 404)


def test_rename_user(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    renamed = user_service.rename_user(session, user.id, "Ada Lovelace")
    assert renamed.display_name == "Ada Lovelace"


def test_rename_user_allows_an_unchanged_name(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    assert user_service.rename_user(session, user.id, "Ada").display_name == "Ada"


def test_rename_user_rejects_a_taken_name(session: Session) -> None:
    user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    with pytest.raises(DuplicateUserNameError):
        user_service.rename_user(session, grace.id, "Ada")


def test_delete_user(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    user_service.delete_user(session, user.id)
    assert list(user_service.list_users(session)) == []


def test_find_user_by_id_and_by_name(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    assert user_service.find_user(session, str(user.id)) is user
    assert user_service.find_user(session, "Ada") is user
    assert user_service.find_user(session, "9999") is None
    assert user_service.find_user(session, "Nobody") is None


def test_first_user_is_the_earliest(session: Session) -> None:
    ada = user_service.create_user(session, "Ada")
    user_service.create_user(session, "Grace")
    assert user_service.first_user(session) is ada


def test_ensure_default_user_seeds_once(session: Session) -> None:
    seeded = user_service.ensure_default_user(session, "Owner")
    assert seeded.display_name == "Owner"
    assert user_service.ensure_default_user(session, "Someone Else") is seeded


def test_ensure_default_user_falls_back_to_the_os_username(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("keel.services.users.getpass.getuser", lambda: "hostuser")
    assert user_service.ensure_default_user(session, None).display_name == "hostuser"


def test_ensure_default_user_ignores_a_blank_setting(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("keel.services.users.getpass.getuser", lambda: "hostuser")
    assert user_service.ensure_default_user(session, "  ").display_name == "hostuser"
