from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from keel.services.identity import (
    SESSION_COOKIE,
    bind_acting_user,
    finish_lookup,
    reset_acting_user,
    resolve_current_user,
)

_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/login",
        "/forgot-password",
        "/forgot-username",
        "/reset-password",
        "/favicon.ico",
        "/api/v1/login",
        "/api/v1/password-resets",
        "/api/v1/username-lookups",
    }
)
_JSON_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})


class RequireLogin:
    """Reject anonymous requests except health, login, and static assets."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_public(scope["path"]):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        factory = request.app.state.session_factory
        with factory() as session:
            user = resolve_current_user(
                session,
                authorization=request.headers.get("authorization"),
                session_cookie=request.cookies.get(SESSION_COOKIE),
                touch=False,
            )
            # Copy the id and name before the lookup session closes. A sync
            # route runs in a worker thread that cannot see a context var set
            # inside that worker, so the bind has to happen on this task.
            token = bind_acting_user(user)
            signed_in = user is not None
            finish_lookup(session)
        try:
            if signed_in:
                await self.app(scope, receive, send)
                return
            response: Response
            if _wants_json(scope["path"]):
                response = JSONResponse({"detail": "Sign in."}, status_code=401)
            else:
                response = RedirectResponse(_login_location(scope), status_code=303)
            await response(scope, receive, send)
        finally:
            reset_acting_user(token)


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith("/assets/")


def _wants_json(path: str) -> bool:
    return path.startswith("/api/") or path in _JSON_PATHS


def _login_location(scope: Scope) -> str:
    path = scope.get("path") or "/"
    if not isinstance(path, str):
        path = "/"
    query = scope.get("query_string", b"")
    if isinstance(query, bytes) and query:
        target = path + "?" + query.decode()
    else:
        target = path
    return "/login?next=" + quote(target, safe="")
