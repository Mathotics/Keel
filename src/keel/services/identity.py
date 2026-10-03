from contextvars import ContextVar, Token

from sqlalchemy.orm import Session

from keel.db.models import User
from keel.services import auth as auth_service

SESSION_COOKIE = "keel_session"
TOKEN_FLASH_COOKIE = "keel_token_flash"

_acting_display_name: ContextVar[str | None] = ContextVar(
    "keel_acting_display_name",
    default=None,
)


def bind_acting_user(user: User | None) -> Token[str | None]:
    name = None if user is None else user.display_name
    return _acting_display_name.set(name)


def reset_acting_user(token: Token[str | None] | None = None) -> None:
    """Clear the bound actor. Token reset can fail across TestClient contexts."""
    if token is not None:
        try:
            _acting_display_name.reset(token)
            return
        except ValueError:
            pass
    _acting_display_name.set(None)


def acting_display_name() -> str | None:
    return _acting_display_name.get()


def resolve_current_user(
    session: Session,
    *,
    authorization: str | None,
    session_cookie: str | None,
) -> User | None:
    """The caller is a bearer token or a session cookie. Nothing else counts.

    A present Authorization header that is not a valid token does not fall
    through to the cookie.
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return auth_service.user_for_api_token(session, token.strip())
    if session_cookie:
        return auth_service.user_for_session(session, session_cookie)
    return None
