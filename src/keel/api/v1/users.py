from fastapi import APIRouter, status

from keel.api.v1.deps import ActingUserDep, SessionDep
from keel.domain.access import Permission
from keel.domain.errors import CannotDeleteSelfError, PermissionDeniedError
from keel.schemas.access import PasswordReset
from keel.schemas.user import UserCreate, UserRead, UserUpdate
from keel.services import access as access_service
from keel.services import users as user_service
from keel.services.access import DENIED

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(session: SessionDep) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in user_service.list_users(session)]


def _access(session: SessionDep, acting: ActingUserDep) -> access_service.Access:
    if acting is None:
        raise PermissionDeniedError(DENIED)
    return access_service.load_access(session, acting.id)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    session: SessionDep,
    acting: ActingUserDep,
) -> UserRead:
    access_service.require(_access(session, acting), Permission.CREATE_USERS)
    user = user_service.create_user(
        session,
        payload.display_name,
        payload.username,
        payload.password,
        require_password=True,
    )
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead)
def read_user(user_id: int, session: SessionDep) -> UserRead:
    return UserRead.model_validate(user_service.get_user(session, user_id))


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    session: SessionDep,
    acting: ActingUserDep,
) -> UserRead:
    access_service.require(_access(session, acting), Permission.RENAME_USERS)
    user = user_service.rename_user(session, user_id, payload.display_name)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    session: SessionDep,
    acting: ActingUserDep,
) -> None:
    access = _access(session, acting)
    if acting is not None and acting.id == user_id:
        raise CannotDeleteSelfError(
            "Sign in as someone else before deleting this account.",
        )
    access_service.assert_may_delete_user(session, access, user_id)
    user_service.delete_user(session, user_id)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int,
    payload: PasswordReset,
    session: SessionDep,
    acting: ActingUserDep,
) -> None:
    access_service.reset_user_password(
        session,
        _access(session, acting),
        user_id,
        payload.password,
        payload.confirm,
    )
