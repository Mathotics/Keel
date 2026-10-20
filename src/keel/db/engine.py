import os
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
    # A file database pays a full fsync on every commit under the default
    # DELETE journal. WAL plus NORMAL keeps those commits durable across an
    # application crash without that stall. In-memory databases have no file.
    database_file = cursor.execute("PRAGMA database_list").fetchone()
    if database_file is not None and database_file[2]:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    # Tests set this so a throwaway file database does not fsync every write.
    # A server must leave it unset.
    if os.environ.get("KEEL_FAST_SQLITE") == "1":
        cursor.execute("PRAGMA synchronous=OFF")
    cursor.close()


def _sqlite_memory(url: str) -> bool:
    """True for ``:memory:`` and for a shared-cache ``file:`` URI."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return False
    database = parsed.database or ""
    if database in ("", ":memory:"):
        return True
    if parsed.query.get("mode") == "memory":
        return True
    return database.startswith("file:") and "mode=memory" in database


def database_file(url: str) -> Path | None:
    """The file a SQLite URL points at, or None for in-memory and other engines."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return None
    if _sqlite_memory(url):
        return None
    if not parsed.database:
        return None
    return Path(parsed.database)


def ensure_database_directory(url: str) -> None:
    path = database_file(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {}
    # A shared-cache memory database is opened from the app thread as well as
    # the test thread. SQLite refuses to reuse a connection across threads.
    if _sqlite_memory(url):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    event.listen(engine, "connect", _configure_sqlite)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
