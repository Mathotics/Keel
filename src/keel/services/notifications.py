"""Inbox storage and preference defaults.

This module records and expires notices. It does not watch issue changes,
send email, or deliver a phone alert.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Notice, NotificationPreference
from keel.db.models.user import utc_now
from keel.domain.enums import NotificationType
from keel.domain.errors import (
    InvalidNotificationError,
    InvalidNotificationPreferenceError,
    NotFoundError,
)
from keel.services import users as user_service
from keel.settings import KeelSettings


@dataclass(frozen=True)
class PreferenceChoice:
    """The channels one type uses for one person."""

    type: NotificationType
    email: bool
    phone: bool
    bell: bool


def add_notice(
    session: Session,
    *,
    recipient_id: int,
    notice_type: NotificationType,
    actor_name: str,
    issue_key: str,
    issue_title: str,
    actor_id: int | None = None,
    issue_id: int | None = None,
    body: str = "",
    deliver_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Notice:
    """Store one inbox row. Callers decide who should receive it."""
    user_service.get_user(session, recipient_id)
    if actor_id is not None:
        user_service.get_user(session, actor_id)
    name = _required(actor_name, "An actor name is required.")
    key = _required(issue_key, "An issue key is required.")
    title = _required(issue_title, "An issue title is required.")
    if len(name) > 100:
        raise InvalidNotificationError("An actor name is at most 100 characters.")
    if len(key) > 32:
        raise InvalidNotificationError("An issue key is at most 32 characters.")
    if len(title) > 300:
        raise InvalidNotificationError("An issue title is at most 300 characters.")
    notice = Notice(
        recipient_id=recipient_id,
        notice_type=notice_type.value,
        actor_id=actor_id,
        actor_name=name,
        issue_id=issue_id,
        issue_key=key,
        issue_title=title,
        body=body,
        created_at=_stored(created_at if created_at is not None else utc_now()),
        deliver_at=None if deliver_at is None else _stored(deliver_at),
    )
    session.add(notice)
    session.flush()
    return notice


def list_notices(session: Session, recipient_id: int) -> Sequence[Notice]:
    """Newest first for one person."""
    user_service.get_user(session, recipient_id)
    return session.scalars(
        select(Notice)
        .where(Notice.recipient_id == recipient_id)
        .order_by(Notice.created_at.desc(), Notice.id.desc()),
    ).all()


def mark_read(session: Session, recipient_id: int, notice_id: int) -> Notice:
    """Stamp the first time this person opened the notice. Later opens keep it."""
    notice = _owned(session, recipient_id, notice_id)
    if notice.read_at is None:
        notice.read_at = _stored(utc_now())
        session.flush()
    return notice


def delete_notice(session: Session, recipient_id: int, notice_id: int) -> None:
    notice = _owned(session, recipient_id, notice_id)
    session.delete(notice)
    session.flush()


def effective_preferences(
    session: Session,
    user_id: int,
) -> list[PreferenceChoice]:
    """Every type, in grid order. A missing row is the default."""
    user_service.get_user(session, user_id)
    stored = {
        row.notice_type: row
        for row in session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
            ),
        )
    }
    choices: list[PreferenceChoice] = []
    for notice_type in NotificationType:
        row = stored.get(notice_type.value)
        if row is None:
            choices.append(_default(notice_type))
        else:
            choices.append(
                PreferenceChoice(
                    type=notice_type,
                    email=row.email,
                    phone=row.phone,
                    bell=row.bell,
                ),
            )
    return choices


def channels_for(
    session: Session,
    user_id: int,
    notice_type: NotificationType,
) -> PreferenceChoice:
    """The channels in force for one type. Missing means the default."""
    user_service.get_user(session, user_id)
    row = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notice_type == notice_type.value,
        ),
    )
    if row is None:
        return _default(notice_type)
    return PreferenceChoice(
        type=notice_type,
        email=row.email,
        phone=row.phone,
        bell=row.bell,
    )


def replace_preferences(
    session: Session,
    user_id: int,
    choices: Sequence[PreferenceChoice],
) -> list[PreferenceChoice]:
    """Replace the whole grid. A type left at the default stores no row."""
    user_service.get_user(session, user_id)
    _require_complete(choices)
    stored = {
        row.notice_type: row
        for row in session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
            ),
        )
    }
    for choice in choices:
        row = stored.get(choice.type.value)
        if _is_default(choice):
            if row is not None:
                session.delete(row)
            continue
        if row is None:
            session.add(
                NotificationPreference(
                    user_id=user_id,
                    notice_type=choice.type.value,
                    email=choice.email,
                    phone=choice.phone,
                    bell=choice.bell,
                ),
            )
            continue
        row.email = choice.email
        row.phone = choice.phone
        row.bell = choice.bell
    session.flush()
    return effective_preferences(session, user_id)


def purge_expired(
    session: Session,
    settings: KeelSettings,
    *,
    now: datetime | None = None,
) -> int:
    """Delete notices whose stored times have passed a cap that is turned on.

    The clock is the row's created_at and read_at, so a server restart does
    not give a notice a new life. A due time for email or a phone alert is
    not a retention clock.
    """
    moment = _aware(now if now is not None else utc_now())
    removed = 0
    for notice in session.scalars(select(Notice)).all():
        expiry = expires_at(notice, settings)
        if expiry is not None and moment >= expiry:
            session.delete(notice)
            removed += 1
    session.flush()
    return removed


def expires_at(notice: Notice, settings: KeelSettings) -> datetime | None:
    """The earlier deadline that is turned on, or none when both caps are off."""
    deadlines: list[datetime] = []
    issued_days = max(settings.notification_issued_retention_days, 0)
    read_days = max(settings.notification_read_retention_days, 0)
    if issued_days:
        deadlines.append(_aware(notice.created_at) + timedelta(days=issued_days))
    if read_days and notice.read_at is not None:
        deadlines.append(_aware(notice.read_at) + timedelta(days=read_days))
    if not deadlines:
        return None
    return min(deadlines)


def _owned(session: Session, recipient_id: int, notice_id: int) -> Notice:
    notice = session.get(Notice, notice_id)
    if notice is None or notice.recipient_id != recipient_id:
        raise NotFoundError("That notification does not exist.")
    return notice


def _default(notice_type: NotificationType) -> PreferenceChoice:
    return PreferenceChoice(
        type=notice_type,
        email=False,
        phone=False,
        bell=True,
    )


def _is_default(choice: PreferenceChoice) -> bool:
    return not choice.email and not choice.phone and choice.bell


def _require_complete(choices: Sequence[PreferenceChoice]) -> None:
    if len(choices) != len(NotificationType):
        raise InvalidNotificationPreferenceError(
            "Choose every notification type.",
        )
    seen: set[NotificationType] = set()
    for choice in choices:
        if choice.type in seen:
            raise InvalidNotificationPreferenceError(
                "Each notification type is listed once.",
            )
        seen.add(choice.type)
    if seen != set(NotificationType):
        raise InvalidNotificationPreferenceError("Choose every notification type.")


def _required(value: str, message: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidNotificationError(message)
    return cleaned


def _stored(value: datetime) -> datetime:
    """Naive UTC, which is what SQLite hands back."""
    return _aware(value).replace(tzinfo=None)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
