from fastapi import FastAPI

from keel.api import health, routes
from keel.settings import KeelSettings, get_settings


def create_app(settings: KeelSettings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    application = FastAPI(title="Keel", version="0.1.0")
    application.state.settings = settings
    application.include_router(health.router)
    application.include_router(routes.router)
    return application


app = create_app()
