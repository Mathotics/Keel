from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from keel.app import create_app
from keel.db.base import Base
from keel.db.engine import create_db_engine, create_session_factory
from keel.settings import KeelSettings

TEST_LAYERS = ("unit", "integration", "system")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = set(item.path.parts)
        for layer in TEST_LAYERS:
            if layer in parts:
                item.add_marker(getattr(pytest.mark, layer))
                break


@pytest.fixture
def settings(tmp_path: Path) -> KeelSettings:
    """Settings pointed at a throwaway database file."""
    url = f"sqlite+pysqlite:///{(tmp_path / 'keel.db').as_posix()}"
    return KeelSettings(_env_file=None, database_url=url, default_user="Tester")


@pytest.fixture
def engine(settings: KeelSettings) -> Iterator[Engine]:
    engine = create_db_engine(settings.resolved_database_url())
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


@pytest.fixture
def app(settings: KeelSettings, engine: Engine) -> FastAPI:
    """An application whose schema already exists, built on the temp database."""
    return create_app(settings)
