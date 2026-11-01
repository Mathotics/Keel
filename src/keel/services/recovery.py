import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from keel.db.models import PasswordResetToken, User
from keel.db.models.user import utc_now
from keel.domain.errors import (
    DomainError,
    InvalidPasswordError,
    PasswordMismatchError,
)
from keel.services import auth as auth_service
from keel.services import mail
from keel.services import users as user_service
from keel.services.passwords import validate_password, verify_password

RESET_NOTICE = "If that username has an email on file, a reset link was sent."
LOOKUP_NOTICE = "If that address is on a profile, the username was sent."
INVALID_LINK = "This reset link is no longer valid."
LINK_TTL = timedelta(hours=1)


class ResetLinkInvalidError(DomainError):
    code = "account.reset_link"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(INVALID_LINK)


def request_password_reset(session: Session, username: str, link_base: str) -> None:
    """Send a one-hour link when the username has an email. Otherwise do nothing."""
    user = user_service.find_by_username(session, username)
    if user is None or not user.email.strip():
        return
    session.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ),
    )
    raw = secrets.token_urlsafe(32)
    now = utc_now()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_digest(raw),
            created_at=now,
            expires_at=now + LINK_TTL,
        ),
    )
    session.flush()
    link = link_base.rstrip("/") + "/reset-password?token=" + quote(raw, safe="")
    mail.send(
        user.email,
        "Reset your Keel password",
        (
            f"A password reset was requested for {user.username}.\n\n"
            "Open this link to choose a new password. It works for one hour.\n\n"
            f"{link}\n"
        ),
    )


def request_username(session: Session, email: str) -> None:
    """Email the username when one profile has this address. Otherwise do nothing."""
    user = user_service.find_by_email(session, email)
    if user is None or not user.email.strip():
        return
    mail.send(
        user.email,
        "Your Keel username",
        f"Your Keel username is {user.username}.\n",
    )


def reset_user(session: Session, raw_token: str) -> User | None:
    """The person a live link belongs to, or None when the link is no longer valid."""
    row = _token(session, raw_token)
    if row is None or not _live(row):
        return None
    return session.get(User, row.user_id)


def complete_password_reset(
    session: Session,
    raw_token: str,
    new: str,
    confirm: str,
) -> str:
    """Replace the password and return a new browser session secret.

    A password that fails the rules leaves the link unused.
    """
    row = _token(session, raw_token)
    if row is None or not _live(row):
        raise ResetLinkInvalidError()
    user = session.get(User, row.user_id)
    if user is None:
        raise ResetLinkInvalidError()
    if new != confirm:
        raise PasswordMismatchError("The new passwords do not match.")
    validate_password(new, user.username)
    if user.password_hash and verify_password(user.password_hash, new):
        raise InvalidPasswordError("Choose a different password.")
    user_service.set_password(session, user, new)
    row.used_at = utc_now()
    session.flush()
    auth_service.revoke_sessions(session, user.id)
    return auth_service.start_session(session, user)


def _token(session: Session, raw_token: str) -> PasswordResetToken | None:
    if not raw_token:
        return None
    return session.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _digest(raw_token)
        ),
    ).first()


def _live(row: PasswordResetToken) -> bool:
    if row.used_at is not None:
        return False
    return _aware(row.expires_at) > utc_now()


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
