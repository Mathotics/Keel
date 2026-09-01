from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from keel.domain.errors import DomainError
from keel.services import users as user_service
from keel.web.context import USER_COOKIE, SessionDep

router = APIRouter(prefix="/web")

SEE_OTHER = 303


def _back(path: str, error: str | None = None) -> RedirectResponse:
    target = path if not error else f"{path}?{urlencode({'error': error})}"
    return RedirectResponse(url=target, status_code=SEE_OTHER)


@router.post("/user")
def switch_user(
    user: Annotated[str, Form()],
    return_to: Annotated[str, Form(alias="next")] = "/",
) -> RedirectResponse:
    response = _back(return_to or "/")
    response.set_cookie(USER_COOKIE, user, samesite="lax")
    return response


@router.post("/users")
def create_user(
    session: SessionDep,
    display_name: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        user_service.create_user(session, display_name)
    except DomainError as exc:
        session.rollback()
        return _back("/users", exc.message)
    return _back("/users")


@router.post("/users/{user_id}/rename")
def rename_user(
    session: SessionDep,
    user_id: int,
    display_name: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        user_service.rename_user(session, user_id, display_name)
    except DomainError as exc:
        session.rollback()
        return _back("/users", exc.message)
    return _back("/users")


@router.post("/users/{user_id}/delete")
def delete_user(session: SessionDep, user_id: int) -> RedirectResponse:
    try:
        user_service.delete_user(session, user_id)
    except DomainError as exc:
        session.rollback()
        return _back("/users", exc.message)
    return _back("/users")
