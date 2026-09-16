from contextvars import ContextVar, Token

from sqlalchemy.orm import Session

from keel.db.models import User
from keel.services import users as user_service

USER_COOKIE = "keel_user"
USER_HEADER = "X-Keel-User"

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
    header: str | None,
    cookie: str | None,
    configured: str | None,
) -> User | None:
    """Identity is declared, not verified: header, cookie, setting, then seed.

    Both the pages and the JSON API resolve the acting user this way, so it
    lives here rather than in either transport layer.
    """
    for token in (header, cookie, configured):
        if token:
            found = user_service.find_user(session, token)
            if found is not None:
                return found
    return user_service.first_user(session)
