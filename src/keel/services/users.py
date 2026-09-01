import getpass
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import User
from keel.domain.errors import DomainError, DuplicateUserNameError, NotFoundError

MAX_NAME_LENGTH = 100


class InvalidUserNameError(DomainError):
    code = "user.invalid_name"
    status_code = 422


def list_users(session: Session) -> Sequence[User]:
    return session.scalars(select(User).order_by(User.display_name)).all()


def first_user(session: Session) -> User | None:
    return session.scalars(select(User).order_by(User.id)).first()


def get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}.")
    return user


def find_user(session: Session, token: str) -> User | None:
    """Resolve a user by identifier or by display name, for header and cookie values."""
    if token.isdigit():
        by_id = session.get(User, int(token))
        if by_id is not None:
            return by_id
    return session.scalars(select(User).where(User.display_name == token)).first()


def create_user(session: Session, display_name: str) -> User:
    name = _clean_name(display_name)
    _reject_duplicate(session, name)
    user = User(display_name=name)
    session.add(user)
    session.flush()
    return user


def rename_user(session: Session, user_id: int, display_name: str) -> User:
    user = get_user(session, user_id)
    name = _clean_name(display_name)
    if name != user.display_name:
        _reject_duplicate(session, name)
        user.display_name = name
    session.flush()
    return user


def delete_user(session: Session, user_id: int) -> None:
    session.delete(get_user(session, user_id))
    session.flush()


def ensure_default_user(session: Session, preferred: str | None) -> User:
    """Guarantee the picker is never empty on a fresh database."""
    existing = first_user(session)
    if existing is not None:
        return existing
    name = (preferred or "").strip() or _os_username()
    return create_user(session, name)


def _os_username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - depends on the host environment
        return "Owner"


def _clean_name(display_name: str) -> str:
    name = display_name.strip()
    if not name:
        raise InvalidUserNameError("A user needs a display name.")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidUserNameError(
            f"A display name may be at most {MAX_NAME_LENGTH} characters.",
            limit=MAX_NAME_LENGTH,
        )
    return name


def _reject_duplicate(session: Session, name: str) -> None:
    taken = session.scalars(select(User).where(User.display_name == name)).first()
    if taken is not None:
        raise DuplicateUserNameError(f"{name} is already taken.", display_name=name)
