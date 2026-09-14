from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from keel.db.models import User
from keel.services.auto_sprint import get_session
from keel.services.identity import (
    USER_COOKIE,
    USER_HEADER,
    bind_acting_user,
    resolve_current_user,
)


def get_request_session(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Session:
    """Bind the acting user after auto-sprint catch-up so history names a person."""
    bind_acting_user(
        resolve_current_user(
            session,
            header=request.headers.get(USER_HEADER),
            cookie=request.cookies.get(USER_COOKIE),
            configured=request.app.state.settings.default_user,
        ),
    )
    return session


SessionDep = Annotated[Session, Depends(get_request_session)]


def get_acting_user(request: Request, session: SessionDep) -> User | None:
    """The same ambient identity the pages use, so the API defaults reporters."""
    return resolve_current_user(
        session,
        header=request.headers.get(USER_HEADER),
        cookie=request.cookies.get(USER_COOKIE),
        configured=request.app.state.settings.default_user,
    )


ActingUserDep = Annotated[User | None, Depends(get_acting_user)]
