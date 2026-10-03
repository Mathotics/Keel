import pytest
from sqlalchemy.orm import Session

from keel.domain.errors import InvalidPasswordError
from keel.services import auth as auth_service
from keel.services import users as user_service
from keel.services.auth import LoginRefused
from keel.services.passwords import hash_password, verify_password


def test_a_password_round_trips() -> None:
    stored = hash_password("correct horse battery")
    assert verify_password(stored, "correct horse battery")
    assert not verify_password(stored, "wrong horse battery")


def test_a_short_password_is_refused(session: Session) -> None:
    with pytest.raises(InvalidPasswordError) as excinfo:
        user_service.create_user(
            session,
            "Ada",
            password="short",
            require_password=True,
        )
    assert excinfo.value.code == "user.invalid_password"


def test_a_password_must_not_match_the_username(session: Session) -> None:
    with pytest.raises(InvalidPasswordError):
        user_service.create_user(
            session,
            "Ada Lovelace",
            username="Ada Lovelace",
            password="ada lovelace",
            require_password=True,
        )


def test_login_uses_one_message_for_unknown_and_wrong(session: Session) -> None:
    auth_service.reset_attempts()
    user_service.create_user(session, "Ada", password="correct horse battery")
    with pytest.raises(LoginRefused) as missing:
        auth_service.authenticate(session, "Grace", "correct horse battery")
    with pytest.raises(LoginRefused) as wrong:
        auth_service.authenticate(session, "Ada", "wrong horse battery staple")
    assert missing.value.message == wrong.value.message
    auth_service.reset_attempts()


def test_too_many_failures_lock_the_username(session: Session) -> None:
    auth_service.reset_attempts()
    user_service.create_user(session, "Ada", password="correct horse battery")
    for _ in range(auth_service.MAX_FAILURES):
        with pytest.raises(LoginRefused) as excinfo:
            auth_service.authenticate(session, "Ada", "wrong horse battery staple")
        assert excinfo.value.message == auth_service.GENERIC_LOGIN_FAILURE
    with pytest.raises(LoginRefused) as locked:
        auth_service.authenticate(session, "Ada", "correct horse battery")
    assert locked.value.message == auth_service.LOCKED_LOGIN
    auth_service.reset_attempts()


def test_changing_a_password_requires_the_current_one(session: Session) -> None:
    auth_service.reset_attempts()
    user = user_service.create_user(session, "Ada", password="correct horse battery")
    with pytest.raises(Exception, match="current password"):
        auth_service.change_password(
            session,
            user,
            "nope nope nope",
            "a different secret",
            "a different secret",
        )
    token = auth_service.change_password(
        session,
        user,
        "correct horse battery",
        "a different secret",
        "a different secret",
    )
    assert auth_service.user_for_session(session, token) is user
    auth_service.reset_attempts()
