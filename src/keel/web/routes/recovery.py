from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from keel.domain.errors import DomainError
from keel.paths import copyright_notice
from keel.services import recovery as recovery_service
from keel.services.recovery import INVALID_LINK, LOOKUP_NOTICE, RESET_NOTICE
from keel.version import package_version
from keel.web.context import SessionDep, get_templates
from keel.web.routes.account import _attach_session, _query

router = APIRouter()
SEE_OTHER = 303


def _page(request: Request, template: str, **context: object) -> HTMLResponse:
    return get_templates().TemplateResponse(
        request,
        template,
        {
            "request": request,
            "version": package_version(),
            "copyright_notice": copyright_notice(),
            **context,
        },
    )


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(
    request: Request,
    error: str | None = None,
    sent: str | None = None,
) -> HTMLResponse:
    return _page(
        request,
        "forgot_password.html",
        error=error,
        notice=RESET_NOTICE if sent else None,
    )


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()] = "",
) -> RedirectResponse:
    login = username.strip()
    if not login:
        return RedirectResponse(
            "/forgot-password?error=" + _query("Enter a username."),
            status_code=SEE_OTHER,
        )
    recovery_service.request_password_reset(session, login, str(request.base_url))
    return RedirectResponse("/forgot-password?sent=1", status_code=SEE_OTHER)


@router.get("/forgot-username", response_class=HTMLResponse)
def forgot_username_page(
    request: Request,
    error: str | None = None,
    sent: str | None = None,
) -> HTMLResponse:
    return _page(
        request,
        "forgot_username.html",
        error=error,
        notice=LOOKUP_NOTICE if sent else None,
    )


@router.post("/forgot-username")
def forgot_username_submit(
    request: Request,
    session: SessionDep,
    email: Annotated[str, Form()] = "",
) -> RedirectResponse:
    address = email.strip()
    if not address:
        return RedirectResponse(
            "/forgot-username?error=" + _query("Enter an email address."),
            status_code=SEE_OTHER,
        )
    recovery_service.request_username(session, address)
    return RedirectResponse("/forgot-username?sent=1", status_code=SEE_OTHER)


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(
    request: Request,
    session: SessionDep,
    token: str = "",
    error: str | None = None,
) -> HTMLResponse:
    if recovery_service.reset_user(session, token) is None:
        return _page(request, "reset_password.html", invalid=INVALID_LINK, token="")
    return _page(request, "reset_password.html", invalid=None, token=token, error=error)


@router.post("/reset-password", response_model=None)
def reset_password_submit(
    request: Request,
    session: SessionDep,
    token: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
) -> RedirectResponse | HTMLResponse:
    try:
        secret = recovery_service.complete_password_reset(
            session,
            token,
            new_password,
            confirm_password,
        )
    except recovery_service.ResetLinkInvalidError:
        session.rollback()
        return _page(request, "reset_password.html", invalid=INVALID_LINK, token="")
    except DomainError as exc:
        session.rollback()
        target = (
            "/reset-password?token=" + _query(token) + "&error=" + _query(exc.message)
        )
        return RedirectResponse(target, status_code=SEE_OTHER)
    response = RedirectResponse("/", status_code=SEE_OTHER)
    _attach_session(response, secret, request)
    return response
