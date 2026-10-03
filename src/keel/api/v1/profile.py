from fastapi import APIRouter, HTTPException, Request, Response, status

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.domain.errors import NotFoundError
from keel.schemas.user import (
    PasswordChange,
    ProfileUpdate,
    TokenCreate,
    TokenCreated,
    TokenRead,
    UserRead,
)
from keel.services import auth as auth_service
from keel.services import users as user_service
from keel.services.auth import SESSION_MAX_AGE, LoginRefused
from keel.services.identity import SESSION_COOKIE

router = APIRouter(prefix="/profile", tags=["profile"])


def _user(acting: ActingUserDep) -> int:
    if acting is None:
        raise NotFoundError("Sign in.")
    return acting.id


@router.get("", response_model=UserRead)
def read_profile(session: SessionDep, acting: ActingUserDep) -> UserRead:
    return UserRead.model_validate(user_service.get_user(session, _user(acting)))


@router.patch("", response_model=UserRead)
def update_profile(
    payload: ProfileUpdate,
    session: SessionDep,
    acting: ActingUserDep,
) -> UserRead:
    user = user_service.update_identity(
        session,
        _user(acting),
        display_name=payload.display_name,
        username=payload.username,
    )
    return UserRead.model_validate(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    request: Request,
    session: SessionDep,
    acting: ActingUserDep,
) -> Response:
    fresh = user_service.get_user(session, _user(acting))
    try:
        token = auth_service.change_password(
            session,
            fresh,
            payload.current_password,
            payload.new_password,
            payload.confirm_password,
        )
    except LoginRefused as exc:
        session.rollback()
        raise HTTPException(status_code=429, detail=exc.message) from exc
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if request.cookies.get(SESSION_COOKIE):
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
    return response


@router.get("/tokens", response_model=list[TokenRead])
def list_tokens(session: SessionDep, acting: ActingUserDep) -> list[TokenRead]:
    rows = auth_service.list_tokens(session, _user(acting))
    return [TokenRead.model_validate(row) for row in rows]


@router.post(
    "/tokens",
    response_model=TokenCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_token(
    payload: TokenCreate,
    session: SessionDep,
    acting: ActingUserDep,
) -> TokenCreated:
    fresh = user_service.get_user(session, _user(acting))
    issued = auth_service.create_token(session, fresh, payload.label)
    body = TokenRead.model_validate(issued.row).model_dump()
    body["token"] = issued.secret
    return TokenCreated.model_validate(body)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: int, session: SessionDep, acting: ActingUserDep) -> None:
    auth_service.revoke_token(session, _user(acting), token_id)
