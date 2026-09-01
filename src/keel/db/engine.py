import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 5000


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    """SQLite ignores foreign keys unless each connection opts in."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cursor.close()


def database_file(url: str) -> Path | None:
    """The file a SQLite URL points at, or None for in-memory and other engines."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return None
    if not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def ensure_database_directory(url: str) -> None:
    path = database_file(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(url: str) -> Engine:
    engine = create_engine(url)
    event.listen(engine, "connect", _configure_sqlite)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
