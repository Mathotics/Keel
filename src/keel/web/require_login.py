from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from keel.services.identity import SESSION_COOKIE, resolve_current_user

_PUBLIC_PATHS = frozenset({"/health", "/login", "/favicon.ico", "/api/v1/login"})
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
            )
            session.commit()
        if user is not None:
            await self.app(scope, receive, send)
            return
        response: Response
        if _wants_json(scope["path"]):
            response = JSONResponse({"detail": "Sign in."}, status_code=401)
        else:
            response = RedirectResponse(_login_location(scope), status_code=303)
        await response(scope, receive, send)


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
