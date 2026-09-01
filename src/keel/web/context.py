from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from keel.db.models import User
from keel.db.session import get_session
from keel.paths import copyright_notice, templates_dir
from keel.services import users as user_service
from keel.version import package_version

USER_COOKIE = "keel_user"
USER_HEADER = "X-Keel-User"


@lru_cache
def get_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(templates_dir()))


def resolve_current_user(
    session: Session,
    *,
    header: str | None,
    cookie: str | None,
    configured: str | None,
) -> User | None:
    """Identity is declared, not verified: header, cookie, setting, then seed."""
    for token in (header, cookie, configured):
        if token:
            found = user_service.find_user(session, token)
            if found is not None:
                return found
    return user_service.first_user(session)


@dataclass(frozen=True)
class Chrome:
    """What the shared bar and footer need on every page."""

    users: Sequence[User]
    current_user: User | None


def get_chrome(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Chrome:
    configured = request.app.state.settings.default_user
    return Chrome(
        users=user_service.list_users(session),
        current_user=resolve_current_user(
            session,
            header=request.headers.get(USER_HEADER),
            cookie=request.cookies.get(USER_COOKIE),
            configured=configured,
        ),
    )


ChromeDep = Annotated[Chrome, Depends(get_chrome)]
SessionDep = Annotated[Session, Depends(get_session)]


def page_context(request: Request, chrome: Chrome, **extra: Any) -> dict[str, Any]:
    return {
        "request": request,
        "version": package_version(),
        "copyright_notice": copyright_notice(),
        "users": chrome.users,
        "current_user": chrome.current_user,
        **extra,
    }
