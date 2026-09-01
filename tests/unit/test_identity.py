from sqlalchemy.orm import Session

from keel.services import users as user_service
from keel.web.context import resolve_current_user


def _resolve(
    session: Session,
    header: str | None = None,
    cookie: str | None = None,
    configured: str | None = None,
) -> str | None:
    found = resolve_current_user(
        session,
        header=header,
        cookie=cookie,
        configured=configured,
    )
    return None if found is None else found.display_name


def test_header_wins_over_cookie_and_setting(session: Session) -> None:
    for name in ("Ada", "Grace", "Alan"):
        user_service.create_user(session, name)
    assert _resolve(session, header="Ada", cookie="Grace", configured="Alan") == "Ada"


def test_cookie_wins_over_the_setting(session: Session) -> None:
    for name in ("Grace", "Alan"):
        user_service.create_user(session, name)
    assert _resolve(session, cookie="Grace", configured="Alan") == "Grace"


def test_setting_is_used_when_nothing_is_declared(session: Session) -> None:
    user_service.create_user(session, "Alan")
    assert _resolve(session, configured="Alan") == "Alan"


def test_unknown_tokens_fall_through_to_the_seeded_user(session: Session) -> None:
    seeded = user_service.create_user(session, "Owner")
    assert _resolve(session, header="ghost", cookie="phantom") == seeded.display_name


def test_no_users_resolves_to_nobody(session: Session) -> None:
    assert _resolve(session, header="Ada") is None
