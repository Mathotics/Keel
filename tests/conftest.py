import os

os.environ.setdefault("KEEL_FAST_PASSWORD_HASH", "1")
os.environ.setdefault("KEEL_FAST_SQLITE", "1")

import uuid
from collections.abc import Iterator

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
def settings() -> KeelSettings:
    """Settings pointed at a throwaway in-memory database.

    A file database spends about a second creating the schema on this machine,
    and nearly every test pays that cost. A named shared-cache database is
    still empty per test, and a second engine (the app opens its own) sees the
    same schema for as long as one connection stays open.
    """
    name = uuid.uuid4().hex
    url = f"sqlite+pysqlite:///file:{name}?mode=memory&cache=shared&uri=true"
    return KeelSettings(_env_file=None, database_url=url, default_user="Tester")


@pytest.fixture
def engine(settings: KeelSettings) -> Iterator[Engine]:
    engine = create_db_engine(settings.resolved_database_url())
    held = engine.connect()
    Base.metadata.create_all(held)
    held.commit()
    yield engine
    held.close()
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
