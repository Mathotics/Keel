import getpass
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from keel.db.models import Comment, Issue, User
from keel.db.models.user import utc_now
from keel.domain.errors import (
    DuplicateUserNameError,
    DuplicateUsernameError,
    InvalidPasswordError,
    InvalidUserNameError,
    InvalidUsernameError,
    NotFoundError,
    PasswordMismatchError,
    UserInUseError,
)
from keel.services.passwords import hash_password, validate_password

SEEDED_USERNAME = "keel"
SEEDED_PASSWORD = "keel"
MAX_NAME_LENGTH = 100


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
    """Resolve a user by identifier or by display name."""
    if token.isdigit():
        by_id = session.get(User, int(token))
        if by_id is not None:
            return by_id
    return session.scalars(select(User).where(User.display_name == token)).first()


def find_by_username(session: Session, username: str) -> User | None:
    login = username.strip().casefold()
    if not login:
        return None
    return session.scalars(
        select(User).where(func.lower(User.username) == login),
    ).first()


def any_password_set(session: Session) -> bool:
    found = session.scalars(
        select(User.id).where(User.password_hash.is_not(None)).limit(1),
    ).first()
    return found is not None


def create_user(
    session: Session,
    display_name: str,
    username: str | None = None,
    password: str | None = None,
    *,
    confirm: str | None = None,
    require_password: bool = False,
) -> User:
    name = _clean_name(display_name)
    login = _clean_username(name if username is None else username)
    _reject_duplicate(session, name)
    _reject_duplicate_username(session, login)
    password_hash = _password_for_create(
        password,
        confirm,
        login,
        require_password=require_password,
    )
    user = User(
        display_name=name,
        username=login,
        password_hash=password_hash,
        updated_at=utc_now(),
    )
    session.add(user)
    session.flush()
    return user


def rename_user(session: Session, user_id: int, display_name: str) -> User:
    user = get_user(session, user_id)
    name = _clean_name(display_name)
    if name != user.display_name:
        _reject_duplicate(session, name)
        user.display_name = name
        user.updated_at = utc_now()
    session.flush()
    return user


def update_identity(
    session: Session,
    user_id: int,
    *,
    display_name: str,
    username: str,
) -> User:
    user = get_user(session, user_id)
    name = _clean_name(display_name)
    login = _clean_username(username)
    if name != user.display_name:
        _reject_duplicate(session, name)
        user.display_name = name
    if login.casefold() != user.username.casefold() or login != user.username:
        _reject_duplicate_username(session, login, except_id=user.id)
        user.username = login
    user.updated_at = utc_now()
    session.flush()
    return user


def set_password(session: Session, user: User, password: str) -> User:
    validate_password(password, user.username)
    user.password_hash = hash_password(password)
    user.updated_at = utc_now()
    session.flush()
    return user


def delete_user(session: Session, user_id: int) -> None:
    user = get_user(session, user_id)
    _reject_while_referenced(session, user)
    session.delete(user)
    session.flush()


def _reject_while_referenced(session: Session, user: User) -> None:
    """A tool with no undo must not quietly orphan an issue's reporter."""
    issues = session.scalars(
        select(Issue).where(
            (Issue.reporter_id == user.id) | (Issue.assignee_id == user.id),
        ),
    ).all()
    comments = session.scalars(
        select(Comment).where(Comment.author_id == user.id),
    ).all()
    if not issues and not comments:
        return
    named = []
    if issues:
        named.append(f"{len(issues)} issue(s)")
    if comments:
        named.append(f"{len(comments)} comment(s)")
    raise UserInUseError(
        f"{user.display_name} is still named on {' and '.join(named)}.",
        user_id=user.id,
        issues=len(issues),
        comments=len(comments),
    )


def ensure_default_user(
    session: Session,
    preferred: str | None,
    *,
    seed_sign_in: bool = True,
) -> User:
    """Guarantee a person exists on a fresh database.

    A database that already has someone is left alone, so production is not
    given the built-in account. On an empty database, a configured name is
    created without a password. Otherwise the built-in ``keel`` account is
    created with its password, unless ``seed_sign_in`` is false, in which case
    the operating-system username is used and still has no password.
    """
    existing = first_user(session)
    if existing is not None:
        return existing
    name = (preferred or "").strip()
    if name:
        return create_user(session, name)
    if seed_sign_in:
        return _seed_sign_in_user(session)
    return create_user(session, _os_username())


def _seed_sign_in_user(session: Session) -> User:
    """The first-run account. Its password is the one exception to the rules."""
    user = create_user(session, SEEDED_USERNAME)
    user.password_hash = hash_password(SEEDED_PASSWORD)
    user.updated_at = utc_now()
    session.flush()
    return user


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


def _clean_username(username: str) -> str:
    name = username.strip()
    if not name:
        raise InvalidUsernameError("A user needs a username.")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidUsernameError(
            f"A username may be at most {MAX_NAME_LENGTH} characters.",
            limit=MAX_NAME_LENGTH,
        )
    if any(ord(character) < 32 for character in name):
        raise InvalidUsernameError("A username cannot contain control characters.")
    return name


def _reject_duplicate_username(
    session: Session,
    username: str,
    *,
    except_id: int | None = None,
) -> None:
    taken = session.scalars(
        select(User).where(func.lower(User.username) == username.casefold()),
    ).first()
    if taken is not None and taken.id != except_id:
        raise DuplicateUsernameError(
            f"{username} is already taken.",
            username=username,
        )


def _password_for_create(
    password: str | None,
    confirm: str | None,
    username: str,
    *,
    require_password: bool,
) -> str | None:
    if not password:
        if require_password:
            raise InvalidPasswordError("A password is required.")
        return None
    if confirm is not None and password != confirm:
        raise PasswordMismatchError("The passwords do not match.")
    validate_password(password, username)
    return hash_password(password)
