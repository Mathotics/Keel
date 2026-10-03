import hashlib
import secrets
import threading
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from keel.db.models import ApiToken, AuthSession, User
from keel.db.models.user import utc_now
from keel.domain.errors import (
    CurrentPasswordError,
    InvalidPasswordError,
    InvalidTokenLabelError,
    NotFoundError,
    PasswordMismatchError,
)
from keel.services import users as user_service
from keel.services.passwords import (
    burn_password_check,
    hash_password,
    needs_rehash,
    verify_password,
)

SESSION_TTL = timedelta(days=14)
SESSION_MAX_AGE = int(SESSION_TTL.total_seconds())
MAX_FAILURES = 8
FAILURE_WINDOW = timedelta(minutes=15)
GENERIC_LOGIN_FAILURE = "Those credentials are not recognized."
LOCKED_LOGIN = "Too many attempts. Try again later."
TOKEN_PREFIX_LENGTH = 12

_attempts: dict[str, list[datetime]] = {}
_attempts_lock = threading.Lock()


class LoginRefused(Exception):
    """A sign-in that must not say whether the username exists."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IssuedToken:
    def __init__(self, row: ApiToken, secret: str) -> None:
        self.row = row
        self.secret = secret


def reset_attempts() -> None:
    with _attempts_lock:
        _attempts.clear()


def authenticate(session: Session, username: str, password: str) -> User:
    login = username.strip()
    key = login.casefold()
    if _is_locked(key):
        raise LoginRefused(LOCKED_LOGIN)
    user = user_service.find_by_username(session, login) if login else None
    if user is None or not _password_matches(user, password):
        if user is None:
            burn_password_check(password)
        _record_failure(key)
        raise LoginRefused(GENERIC_LOGIN_FAILURE)
    _clear_failures(key)
    return user


def change_password(
    session: Session,
    user: User,
    current: str,
    new: str,
    confirm: str,
) -> str:
    """Set a new password and return a fresh session secret."""
    key = user.username.casefold()
    if _is_locked(key):
        raise LoginRefused(LOCKED_LOGIN)
    if not _password_matches(user, current):
        _record_failure(key)
        raise CurrentPasswordError("The current password is wrong.")
    _clear_failures(key)
    if new != confirm:
        raise PasswordMismatchError("The new passwords do not match.")
    if user.password_hash and verify_password(user.password_hash, new):
        raise InvalidPasswordError("Choose a different password.")
    user_service.set_password(session, user, new)
    revoke_sessions(session, user.id)
    return start_session(session, user)


def start_session(session: Session, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    now = utc_now()
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=_digest(raw),
            created_at=now,
            expires_at=now + SESSION_TTL,
            last_seen_at=now,
        ),
    )
    session.flush()
    return raw


def user_for_session(session: Session, raw_token: str) -> User | None:
    if not raw_token:
        return None
    row = session.scalars(
        select(AuthSession).where(AuthSession.token_hash == _digest(raw_token)),
    ).first()
    if row is None:
        return None
    now = utc_now()
    if _aware(row.expires_at) <= now:
        session.delete(row)
        session.flush()
        return None
    row.last_seen_at = now
    session.flush()
    return session.get(User, row.user_id)


def revoke_session_token(session: Session, raw_token: str) -> None:
    if not raw_token:
        return
    session.execute(
        delete(AuthSession).where(AuthSession.token_hash == _digest(raw_token)),
    )
    session.flush()


def revoke_sessions(session: Session, user_id: int) -> None:
    session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    session.flush()


def create_token(session: Session, user: User, label: str) -> IssuedToken:
    cleaned = label.strip()
    if not cleaned:
        raise InvalidTokenLabelError("A token needs a label.")
    if len(cleaned) > 100:
        raise InvalidTokenLabelError("A token label may be at most 100 characters.")
    raw = "keel_" + secrets.token_urlsafe(32)
    now = utc_now()
    row = ApiToken(
        user_id=user.id,
        label=cleaned,
        token_prefix=raw[:TOKEN_PREFIX_LENGTH],
        token_hash=_digest(raw),
        created_at=now,
    )
    session.add(row)
    session.flush()
    return IssuedToken(row, raw)


def list_tokens(session: Session, user_id: int) -> Sequence[ApiToken]:
    return session.scalars(
        select(ApiToken)
        .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at, ApiToken.id),
    ).all()


def revoke_token(session: Session, user_id: int, token_id: int) -> None:
    row = session.get(ApiToken, token_id)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        raise NotFoundError("No such token.")
    row.revoked_at = utc_now()
    session.flush()


def user_for_api_token(session: Session, raw_token: str) -> User | None:
    if not raw_token:
        return None
    row = session.scalars(
        select(ApiToken).where(ApiToken.token_hash == _digest(raw_token)),
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    row.last_used_at = utc_now()
    session.flush()
    user = session.get(User, row.user_id)
    return user


def _password_matches(user: User, password: str) -> bool:
    stored = user.password_hash
    if not stored:
        burn_password_check(password)
        return False
    if not verify_password(stored, password):
        return False
    if needs_rehash(stored):
        user.password_hash = hash_password(password)
    return True


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _record_failure(key: str) -> None:
    now = utc_now()
    with _attempts_lock:
        recent = [stamp for stamp in _attempts.get(key, []) if _within(stamp, now)]
        recent.append(now)
        _attempts[key] = recent


def _clear_failures(key: str) -> None:
    with _attempts_lock:
        _attempts.pop(key, None)


def _is_locked(key: str) -> bool:
    now = utc_now()
    with _attempts_lock:
        recent = [stamp for stamp in _attempts.get(key, []) if _within(stamp, now)]
        _attempts[key] = recent
        return len(recent) >= MAX_FAILURES


def _within(stamp: datetime, now: datetime) -> bool:
    return now - _aware(stamp) < FAILURE_WINDOW
