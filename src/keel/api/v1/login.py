from fastapi import APIRouter, HTTPException

from keel.api.v1.deps import SessionDep
from keel.db.models.user import utc_now
from keel.schemas.user import LoginCreate, LoginRead
from keel.services import auth as auth_service
from keel.services.auth import LOCKED_LOGIN, LoginRefused

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginRead)
def login(payload: LoginCreate, session: SessionDep) -> LoginRead:
    """Check the password and issue a personal token for this device."""
    try:
        user = auth_service.authenticate(session, payload.username, payload.password)
    except LoginRefused as exc:
        code = 429 if exc.message == LOCKED_LOGIN else 401
        raise HTTPException(status_code=code, detail=exc.message) from exc
    issued = auth_service.create_token(session, user, payload.label)
    issued.row.last_used_at = utc_now()
    return LoginRead(
        token=issued.secret,
        token_id=issued.row.id,
        label=issued.row.label,
        username=user.username,
        display_name=user.display_name,
    )
