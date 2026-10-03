from pathlib import Path

from fastapi.testclient import TestClient

from keel.app import app, create_app
from keel.db.base import Base
from keel.db.engine import create_db_engine
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


def test_docs_require_sign_in_and_favicon_does_not(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'docs.db').as_posix()}"
    settings = KeelSettings(_env_file=None, database_url=url, default_user="Tester")
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        assert client.get("/favicon.ico").status_code == 200
        assert client.get("/docs").status_code == 401
        assert client.get("/redoc").status_code == 401
