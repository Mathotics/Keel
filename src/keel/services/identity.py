from sqlalchemy.orm import Session

from keel.db.models import User
from keel.services import users as user_service

USER_COOKIE = "keel_user"
USER_HEADER = "X-Keel-User"


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
