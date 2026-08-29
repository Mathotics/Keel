from fastapi.testclient import TestClient

from keel.app import app, create_app
from keel.settings import KeelSettings
from keel.version import package_version


def test_create_app_uses_provided_settings() -> None:
    settings = KeelSettings(_env_file=None)
    application = create_app(settings)
    assert application.state.settings is settings
    assert application.title == "Keel"
    assert application.version == package_version()


def test_module_app_is_fastapi() -> None:
    assert app.title == "Keel"
    assert app.version == package_version()


def test_docs_and_favicon_routes() -> None:
    client = TestClient(create_app(KeelSettings(_env_file=None)))
    assert client.get("/favicon.ico").status_code == 200
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "/assets/favicon.ico" in docs.text
    redoc = client.get("/redoc")
    assert redoc.status_code == 200
    assert "/assets/favicon.ico" in redoc.text
