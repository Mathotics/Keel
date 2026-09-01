from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from keel.db.base import Base
from keel.db.engine import (
    create_db_engine,
    create_session_factory,
    database_file,
    ensure_database_directory,
)
from keel.domain.errors import DomainError, NotFoundError


def test_database_file_reads_a_sqlite_path(tmp_path: Path) -> None:
    target = tmp_path / "keel.db"
    assert database_file(f"sqlite+pysqlite:///{target.as_posix()}") == target


def test_database_file_is_none_for_memory_and_other_engines() -> None:
    assert database_file("sqlite://") is None
    assert database_file("postgresql://localhost/keel") is None


def test_ensure_database_directory_creates_missing_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "keel.db"
    ensure_database_directory(f"sqlite+pysqlite:///{target.as_posix()}")
    assert target.parent.is_dir()


def test_ensure_database_directory_ignores_memory_urls() -> None:
    ensure_database_directory("sqlite://")


def test_connections_enforce_foreign_keys(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_session_factory_round_trips_a_model(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'roundtrip.db').as_posix()}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        _insert_user(session, "Ada")
        session.commit()
    with factory() as session:
        assert _names(session) == ["Ada"]
    engine.dispose()


def _insert_user(session: Session, name: str) -> None:
    from keel.db.models import User

    session.add(User(display_name=name))


def _names(session: Session) -> list[str]:
    from sqlalchemy import select

    from keel.db.models import User

    return list(session.scalars(select(User.display_name)))


def test_domain_error_carries_a_code_and_context() -> None:
    class Refused(DomainError):
        code = "test.refused"

    error = Refused("No.", subject="thing")
    assert error.status_code == 409
    assert error.as_detail() == {
        "code": "test.refused",
        "message": "No.",
        "context": {"subject": "thing"},
    }


def test_not_found_error_keeps_its_message() -> None:
    assert NotFoundError("gone").message == "gone"


def test_session_dependency_rolls_back_on_failure(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from keel.db.session import get_session

    url = f"sqlite+pysqlite:///{(tmp_path / 'rollback.db').as_posix()}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    request = MagicMock()
    request.app.state.session_factory = create_session_factory(engine)

    generator = get_session(request)
    session = next(generator)
    _insert_user(session, "Ada")
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("boom"))

    with create_session_factory(engine)() as fresh:
        assert _names(fresh) == []
    engine.dispose()
