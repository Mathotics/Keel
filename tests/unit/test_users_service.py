from datetime import date

import pytest
from sqlalchemy.orm import Session

from keel.domain.errors import (
    DuplicateUserNameError,
    InvalidDateOfBirthError,
    InvalidEmailError,
    InvalidPasswordError,
    InvalidProfileNameError,
    InvalidUserNameError,
    NotFoundError,
)
from keel.services import users as user_service
from keel.services.passwords import validate_password, verify_password


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
    assert seeded.password_hash is None
    assert user_service.ensure_default_user(session, "Someone Else") is seeded


def test_an_empty_database_can_sign_in_as_keel(session: Session) -> None:
    seeded = user_service.ensure_default_user(session, None)
    assert seeded.username == "keel"
    assert seeded.display_name == "keel"
    assert seeded.password_hash is not None
    assert verify_password(seeded.password_hash, "keel")
    with pytest.raises(InvalidPasswordError):
        validate_password("keel", "keel")
    assert user_service.ensure_default_user(session, None) is seeded


def test_ensure_default_user_falls_back_to_the_os_username(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("keel.services.users.getpass.getuser", lambda: "hostuser")
    seeded = user_service.ensure_default_user(session, None, seed_sign_in=False)
    assert seeded.display_name == "hostuser"
    assert seeded.password_hash is None


def test_a_new_user_has_blank_contact_fields(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    assert user.email == ""
    assert user.first_name == ""
    assert user.last_name == ""
    assert user.date_of_birth is None


def test_update_identity_sets_and_clears_optional_fields(session: Session) -> None:
    user = user_service.create_user(session, "Ada", username="ada")
    saved = user_service.update_identity(
        session,
        user.id,
        display_name="Ada",
        username="ada",
        email="  Ada@Example.com ",
        first_name=" Ada ",
        last_name="Lovelace",
        date_of_birth=user_service.parse_date_of_birth("1815-12-10"),
    )
    assert saved.email == "Ada@Example.com"
    assert saved.first_name == "Ada"
    assert saved.last_name == "Lovelace"
    assert saved.date_of_birth is not None
    assert saved.date_of_birth.isoformat() == "1815-12-10"

    kept = user_service.update_identity(
        session,
        user.id,
        display_name="Augusta",
        username="ada",
    )
    assert kept.display_name == "Augusta"
    assert kept.email == "Ada@Example.com"
    assert kept.date_of_birth is not None

    cleared = user_service.update_identity(
        session,
        user.id,
        display_name="Augusta",
        username="ada",
        email=None,
        first_name="   ",
        last_name=None,
        date_of_birth=None,
    )
    assert cleared.email == ""
    assert cleared.first_name == ""
    assert cleared.last_name == ""
    assert cleared.date_of_birth is None


def test_update_identity_rejects_a_bad_email(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    with pytest.raises(InvalidEmailError) as excinfo:
        user_service.update_identity(
            session,
            user.id,
            display_name="Ada",
            username="Ada",
            email="not-an-email",
        )
    assert excinfo.value.code == "user.invalid_email"
    assert user.email == ""


def test_update_identity_rejects_a_future_date_of_birth(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    with pytest.raises(InvalidDateOfBirthError):
        user_service.update_identity(
            session,
            user.id,
            display_name="Ada",
            username="Ada",
            date_of_birth=date(2999, 1, 1),
        )
    with pytest.raises(InvalidDateOfBirthError):
        user_service.parse_date_of_birth("1815-13-01")
    assert user_service.parse_date_of_birth("  ") is None
    assert user.date_of_birth is None


def test_update_identity_rejects_an_overlong_first_name(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    with pytest.raises(InvalidProfileNameError) as excinfo:
        user_service.update_identity(
            session,
            user.id,
            display_name="Ada",
            username="Ada",
            first_name="x" * 101,
        )
    assert excinfo.value.code == "user.invalid_profile_name"
    with pytest.raises(InvalidProfileNameError):
        user_service.update_identity(
            session,
            user.id,
            display_name="Ada",
            username="Ada",
            last_name="Ada\nLovelace",
        )


def test_ensure_default_user_ignores_a_blank_setting(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("keel.services.users.getpass.getuser", lambda: "hostuser")
    seeded = user_service.ensure_default_user(session, "  ", seed_sign_in=False)
    assert seeded.display_name == "hostuser"
    assert seeded.password_hash is None
