import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from keel.api import health
from keel.api import v1 as api_v1
from keel.api.errors import register_error_handlers
from keel.db.engine import create_db_engine, create_session_factory
from keel.paths import asset_path, assets_dir
from keel.services import auto_sprint
from keel.services.users import ensure_default_user
from keel.settings import KeelSettings, get_settings
from keel.version import package_version
from keel.web import routes as web_routes


class RevalidatedStaticFiles(StaticFiles):
    """Serve assets with `Cache-Control: no-cache`.

    Starlette sends an ETag and Last-Modified but no Cache-Control, which
    leaves browsers free to cache heuristically and serve a stale stylesheet
    without ever asking whether it changed. `no-cache` still allows caching;
    it only requires revalidation, which costs a 304.
    """

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(settings: KeelSettings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    engine = create_db_engine(settings.resolved_database_url())
    session_factory = create_session_factory(engine)
    default_user = settings.default_user

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        with session_factory() as session:
            ensure_default_user(session, default_user)
            auto_sprint.advance_all(session)
            session.commit()

        async def poll() -> None:
            while True:
                await asyncio.sleep(auto_sprint.POLL_SECONDS)
                try:
                    with session_factory() as session:
                        auto_sprint.advance_all(session)
                        session.commit()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    continue

        task = asyncio.create_task(poll())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    application = FastAPI(
        title="Keel",
        version=package_version(),
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.include_router(health.router)
    application.include_router(api_v1.router)
    application.include_router(web_routes.router)
    register_error_handlers(application)
    _register_docs(application)
    application.mount(
        "/assets",
        RevalidatedStaticFiles(directory=assets_dir()),
        name="assets",
    )
    return application


def _register_docs(application: FastAPI) -> None:
    favicon = asset_path("favicon.ico")
    openapi_url = application.openapi_url or "/openapi.json"

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon_ico() -> FileResponse:
        return FileResponse(favicon, media_type="image/x-icon")

    @application.get("/docs", include_in_schema=False)
    def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=openapi_url,
            title=f"{application.title} - Swagger UI",
            swagger_favicon_url="/assets/favicon.ico",
        )

    @application.get("/redoc", include_in_schema=False)
    def redoc_ui() -> HTMLResponse:
        return get_redoc_html(
            openapi_url=openapi_url,
            title=f"{application.title} - ReDoc",
            redoc_favicon_url="/assets/favicon.ico",
        )


app = create_app()
