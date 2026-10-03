from typing import Annotated
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from keel.domain.errors import DomainError, NotFoundError
from keel.paths import copyright_notice
from keel.services import auth as auth_service
from keel.services import users as user_service
from keel.services.auth import SESSION_MAX_AGE, LoginRefused
from keel.services.identity import SESSION_COOKIE, TOKEN_FLASH_COOKIE
from keel.version import package_version
from keel.web.context import ChromeDep, SessionDep, get_templates, page_context

router = APIRouter()
SEE_OTHER = 303


def safe_next(value: str | None) -> str:
    """A same-site path. Anything else becomes the inbox."""
    if not value:
        return "/"
    candidate = value.strip()
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or candidate.startswith("/\\")
        or "\\" in candidate
    ):
        return "/"
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return "/"
    return candidate


def _secure(request: Request) -> bool:
    return request.url.scheme == "https"


def _attach_session(response: RedirectResponse, token: str, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )


def _clear_session(response: RedirectResponse, request: Request) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        samesite="lax",
        httponly=True,
        secure=_secure(request),
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    session: SessionDep,
    error: str | None = None,
    next: str | None = None,
    username: str = "",
) -> Response:
    current = request.cookies.get(SESSION_COOKIE)
    if current and auth_service.user_for_session(session, current) is not None:
        return RedirectResponse(safe_next(next), status_code=SEE_OTHER)
    return get_templates().TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "version": package_version(),
            "copyright_notice": copyright_notice(),
            "error": error,
            "next": safe_next(next) if next else "",
            "username": username,
            "needs_password": not user_service.any_password_set(session),
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
) -> RedirectResponse:
    destination = safe_next(next)
    try:
        user = auth_service.authenticate(session, username, password)
    except LoginRefused as exc:
        session.rollback()
        target = "/login?error=" + _query(exc.message)
        if username.strip():
            target += "&username=" + _query(username.strip())
        if destination != "/":
            target += "&next=" + _query(destination)
        return RedirectResponse(target, status_code=SEE_OTHER)
    token = auth_service.start_session(session, user)
    response = RedirectResponse(destination, status_code=SEE_OTHER)
    _attach_session(response, token, request)
    return response


@router.post("/logout")
def logout(request: Request, session: SessionDep) -> RedirectResponse:
    auth_service.revoke_session_token(
        session,
        request.cookies.get(SESSION_COOKIE, ""),
    )
    response = RedirectResponse("/login", status_code=SEE_OTHER)
    _clear_session(response, request)
    return response


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    session: SessionDep,
    chrome: ChromeDep,
    error: str | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    user = chrome.current_user
    assert user is not None
    fresh = user_service.get_user(session, user.id)
    new_token = request.cookies.get(TOKEN_FLASH_COOKIE)
    response = get_templates().TemplateResponse(
        request,
        "profile.html",
        page_context(
            request,
            chrome,
            profile=fresh,
            tokens=auth_service.list_tokens(session, fresh.id),
            new_token=new_token,
            error=error,
            notice=notice,
        ),
    )
    if new_token:
        response.delete_cookie(
            TOKEN_FLASH_COOKIE,
            path="/profile",
            samesite="lax",
            httponly=True,
            secure=_secure(request),
        )
    return response


@router.post("/web/profile")
def update_profile(
    session: SessionDep,
    chrome: ChromeDep,
    display_name: Annotated[str, Form()],
    username: Annotated[str, Form()],
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    try:
        user_service.update_identity(
            session,
            user.id,
            display_name=display_name,
            username=username,
        )
    except DomainError as exc:
        session.rollback()
        return _profile(exc.message)
    return _profile(notice="Profile updated.")


@router.post("/web/profile/password")
def update_password(
    request: Request,
    session: SessionDep,
    chrome: ChromeDep,
    current_password: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    fresh = user_service.get_user(session, user.id)
    try:
        token = auth_service.change_password(
            session,
            fresh,
            current_password,
            new_password,
            confirm_password,
        )
    except LoginRefused as exc:
        session.rollback()
        return _profile(exc.message)
    except DomainError as exc:
        session.rollback()
        return _profile(exc.message)
    response = _profile(notice="Password updated.")
    _attach_session(response, token, request)
    return response


@router.post("/web/profile/tokens")
def create_profile_token(
    request: Request,
    session: SessionDep,
    chrome: ChromeDep,
    label: Annotated[str, Form()] = "",
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    fresh = user_service.get_user(session, user.id)
    try:
        issued = auth_service.create_token(session, fresh, label)
    except DomainError as exc:
        session.rollback()
        return _profile(exc.message)
    response = _profile(notice="Copy the new token now. It will not be shown again.")
    response.set_cookie(
        TOKEN_FLASH_COOKIE,
        issued.secret,
        max_age=120,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/profile",
    )
    return response


@router.post("/web/profile/tokens/{token_id}/revoke")
def revoke_profile_token(
    session: SessionDep,
    chrome: ChromeDep,
    token_id: int,
) -> RedirectResponse:
    user = chrome.current_user
    assert user is not None
    try:
        auth_service.revoke_token(session, user.id, token_id)
    except NotFoundError as exc:
        session.rollback()
        return _profile(exc.message)
    except DomainError as exc:
        session.rollback()
        return _profile(exc.message)
    return _profile(notice="Token revoked.")


def _profile(error: str | None = None, notice: str | None = None) -> RedirectResponse:
    from keel.web.routes.forms import _back

    return _back("/profile", error, notice)


def _query(value: str) -> str:
    return quote(value, safe="")
