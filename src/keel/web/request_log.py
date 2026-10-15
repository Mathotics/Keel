"""Record signed-in requests after the response status is known."""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from keel.services.identity import SESSION_COOKIE, resolve_current_user
from keel.services.request_log import (
    begin_capture,
    finish_capture,
    keep_change_note,
    record_request,
    skip_request_path,
)
from keel.settings import KeelSettings


class RequestLogMiddleware:
    """Append one log row for each signed-in request that is worth keeping."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or skip_request_path(scope["path"]):
            await self.app(scope, receive, send)
            return
        identity = _signed_in(scope)
        if identity is None:
            await self.app(scope, receive, send)
            return
        user_id, actor_name = identity
        status_code = 500
        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", "/"))
        token = begin_capture()
        try:

            async def send_wrapper(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = int(message["status"])
                await send(message)

            await self.app(scope, receive, send_wrapper)
        finally:
            note = keep_change_note(method, status_code, finish_capture(token))
            _store(
                scope,
                user_id=user_id,
                actor_name=actor_name,
                method=method,
                path=path,
                status_code=status_code,
                change_note=note,
            )


def _signed_in(scope: Scope) -> tuple[int, str] | None:
    request = Request(scope)
    factory = request.app.state.session_factory
    with factory() as session:
        user = resolve_current_user(
            session,
            authorization=request.headers.get("authorization"),
            session_cookie=request.cookies.get(SESSION_COOKIE),
        )
        if user is None:
            session.rollback()
            return None
        identity = (user.id, user.display_name)
        session.commit()
        return identity


def _store(
    scope: Scope,
    *,
    user_id: int,
    actor_name: str,
    method: str,
    path: str,
    status_code: int,
    change_note: str | None,
) -> None:
    request = Request(scope)
    settings = request.app.state.settings
    if not isinstance(settings, KeelSettings):
        return
    factory = request.app.state.session_factory
    with factory() as session:
        record_request(
            session,
            user_id=user_id,
            actor_name=actor_name,
            method=method,
            path=path,
            status_code=status_code,
            change_note=change_note,
            settings=settings,
        )
        session.commit()
