from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from keel.db.models import User
from keel.services.auto_sprint import get_session
from keel.services.identity import (
    SESSION_COOKIE,
    bind_acting_user,
    resolve_current_user,
)


def get_request_session(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Session:
    """Bind the signed-in user after auto-sprint catch-up so history names a person."""
    bind_acting_user(
        resolve_current_user(
            session,
            authorization=request.headers.get("authorization"),
            session_cookie=request.cookies.get(SESSION_COOKIE),
        ),
    )
    return session


SessionDep = Annotated[Session, Depends(get_request_session)]


def get_acting_user(request: Request, session: SessionDep) -> User | None:
    """The signed-in user, so the API defaults reporters and authors."""
    return resolve_current_user(
        session,
        authorization=request.headers.get("authorization"),
        session_cookie=request.cookies.get(SESSION_COOKIE),
    )


ActingUserDep = Annotated[User | None, Depends(get_acting_user)]
