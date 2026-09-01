from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker


def session_factory_of(request: Request) -> sessionmaker[Session]:
    factory = request.app.state.session_factory
    assert isinstance(factory, sessionmaker)
    return factory


def get_session(request: Request) -> Generator[Session, None, None]:
    """One transaction per request: commit on success, roll back on failure."""
    session = session_factory_of(request)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
