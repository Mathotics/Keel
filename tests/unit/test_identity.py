from sqlalchemy.orm import Session

from keel.services import auth as auth_service
from keel.services import users as user_service
from keel.web.context import resolve_current_user


def _resolve(
    session: Session,
    authorization: str | None = None,
    session_cookie: str | None = None,
) -> str | None:
    found = resolve_current_user(
        session,
        authorization=authorization,
        session_cookie=session_cookie,
    )
    return None if found is None else found.display_name


def test_a_session_cookie_resolves_that_person(session: Session) -> None:
    user = user_service.create_user(session, "Ada")
    raw = auth_service.start_session(session, user)
    assert _resolve(session, session_cookie=raw) == "Ada"


def test_a_bearer_token_wins_over_the_cookie(session: Session) -> None:
    ada = user_service.create_user(session, "Ada")
    grace = user_service.create_user(session, "Grace")
    cookie = auth_service.start_session(session, grace)
    issued = auth_service.create_token(session, ada, "script")
    assert (
        _resolve(
            session,
            authorization=f"Bearer {issued.secret}",
            session_cookie=cookie,
        )
        == "Ada"
    )


def test_a_bad_bearer_token_does_not_fall_through_to_the_cookie(
    session: Session,
) -> None:
    grace = user_service.create_user(session, "Grace")
    cookie = auth_service.start_session(session, grace)
    assert _resolve(session, authorization="Bearer nope", session_cookie=cookie) is None


def test_an_unknown_cookie_is_nobody(session: Session) -> None:
    user_service.create_user(session, "Owner")
    assert _resolve(session, session_cookie="nope") is None


def test_no_credentials_resolve_to_nobody(session: Session) -> None:
    user_service.create_user(session, "Ada")
    assert _resolve(session) is None
