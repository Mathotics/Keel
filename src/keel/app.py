from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from keel.api import health, routes
from keel.paths import asset_path, assets_dir
from keel.settings import KeelSettings, get_settings


def create_app(settings: KeelSettings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    application = FastAPI(
        title="Keel",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    application.state.settings = settings
    application.include_router(health.router)
    application.include_router(routes.router)
    _register_docs(application)
    application.mount(
        "/assets",
        StaticFiles(directory=assets_dir()),
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
