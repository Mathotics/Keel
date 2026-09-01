from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from keel.db.session import get_session
from keel.schemas.user import UserCreate, UserRead, UserUpdate
from keel.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[UserRead])
def list_users(session: SessionDep) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in user_service.list_users(session)]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: SessionDep) -> UserRead:
    user = user_service.create_user(session, payload.display_name)
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead)
def read_user(user_id: int, session: SessionDep) -> UserRead:
    return UserRead.model_validate(user_service.get_user(session, user_id))


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, session: SessionDep) -> UserRead:
    user = user_service.rename_user(session, user_id, payload.display_name)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, session: SessionDep) -> None:
    user_service.delete_user(session, user_id)
