from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from keel.api.v1.deps import SessionDep
from keel.services import recovery as recovery_service
from keel.services.recovery import LOOKUP_NOTICE, RESET_NOTICE

router = APIRouter(tags=["auth"])


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(max_length=100)


class UsernameLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)


class NoticeRead(BaseModel):
    notice: str


@router.post("/password-resets", response_model=NoticeRead)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    session: SessionDep,
) -> NoticeRead:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="Enter a username.")
    recovery_service.request_password_reset(session, username, str(request.base_url))
    return NoticeRead(notice=RESET_NOTICE)


@router.post("/username-lookups", response_model=NoticeRead)
def request_username(
    payload: UsernameLookupRequest,
    session: SessionDep,
) -> NoticeRead:
    email = payload.email.strip()
    if not email:
        raise HTTPException(status_code=422, detail="Enter an email address.")
    recovery_service.request_username(session, email)
    return NoticeRead(notice=LOOKUP_NOTICE)
