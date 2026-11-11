"""Inbox storage, preference defaults, and notification delivery.

A mail or phone failure leaves the inbox row in place.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Notice, NotificationPreference
from keel.db.models.user import utc_now
from keel.domain.enums import NotificationType
from keel.domain.errors import (
    InvalidNotificationError,
    InvalidNotificationPreferenceError,
    NotFoundError,
)
from keel.services import mail
from keel.services import users as user_service
from keel.services.history import SYSTEM_ACTOR
from keel.services.identity import acting_user_id
from keel.settings import KeelSettings, get_settings

logger = logging.getLogger(__name__)


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
    email: bool = False,
    phone: bool = False,
    bell: bool = True,
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
    moment = _stored(created_at if created_at is not None else utc_now())
    notice = Notice(
        recipient_id=recipient_id,
        notice_type=notice_type.value,
        actor_id=actor_id,
        actor_name=name,
        issue_id=issue_id,
        issue_key=key,
        issue_title=title,
        body=body,
        email=email,
        phone=phone,
        bell=bell,
        created_at=moment,
        changed_at=moment,
        deliver_at=None if deliver_at is None else _stored(deliver_at),
    )
    session.add(notice)
    session.flush()
    return notice


def has_unread(session: Session, recipient_id: int) -> bool:
    """Whether this person's inbox has a notice they have not opened."""
    notice_id = session.scalar(
        select(Notice.id)
        .where(
            Notice.recipient_id == recipient_id,
            Notice.read_at.is_(None),
        )
        .limit(1),
    )
    return notice_id is not None


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


def mark_all_read(session: Session, recipient_id: int) -> int:
    """Stamp every unread notice. Viewing the panel does this; deleting does not."""
    user_service.get_user(session, recipient_id)
    pending = session.scalars(
        select(Notice).where(
            Notice.recipient_id == recipient_id,
            Notice.read_at.is_(None),
        ),
    ).all()
    if not pending:
        return 0
    moment = _stored(utc_now())
    for notice in pending:
        notice.read_at = moment
    session.flush()
    return len(pending)


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


_UPDATE_TYPES = (
    NotificationType.UPDATE_ON_CREATED.value,
    NotificationType.UPDATE_ON_ASSIGNED.value,
)
_COMMENT_TYPES = (
    NotificationType.COMMENT_ON_CREATED.value,
    NotificationType.COMMENT_ON_ASSIGNED.value,
)
_DELETE_TYPES = (
    NotificationType.DELETE_ON_CREATED.value,
    NotificationType.DELETE_ON_ASSIGNED.value,
)


def record_comment(
    session: Session,
    issue: Issue,
    body: str,
    *,
    actor_id: int | None,
    now: datetime | None = None,
) -> None:
    """One comment notice for the reporter and the assignee, skipping the author."""
    if actor_id is None:
        return
    _fan_out(
        session,
        issue,
        NotificationType.COMMENT_ON_CREATED,
        NotificationType.COMMENT_ON_ASSIGNED,
        body,
        actor_id=actor_id,
        now=now if now is not None else utc_now(),
        immediate=True,
    )


def record_assignment(
    session: Session,
    issue: Issue,
    *,
    actor_id: int | None,
    now: datetime | None = None,
) -> None:
    """Tell the new assignee. Unassign and self-assign stay quiet."""
    if actor_id is None:
        return
    if issue.assignee_id is None or issue.assignee_id == actor_id:
        return
    moment = now if now is not None else utc_now()
    _deliver(
        session,
        issue,
        issue.assignee_id,
        [NotificationType.ASSIGNED],
        "Assigned to you.",
        actor_id=actor_id,
        now=moment,
        immediate=True,
    )


def record_update(
    session: Session,
    issue: Issue,
    lines: Sequence[str],
    *,
    actor_name: str | None = None,
    actor_id: int | None = None,
    now: datetime | None = None,
    settings: KeelSettings | None = None,
) -> None:
    """One update notice per person. Later edits in the quiet period grow it."""
    if actor_name == SYSTEM_ACTOR or not lines:
        return
    actor = actor_id if actor_id is not None else acting_user_id()
    if actor is None:
        return
    _fan_out(
        session,
        issue,
        NotificationType.UPDATE_ON_CREATED,
        NotificationType.UPDATE_ON_ASSIGNED,
        "\n".join(lines),
        actor_id=actor,
        now=now if now is not None else utc_now(),
        immediate=False,
        settings=settings,
        grow=True,
    )


def record_delete(
    session: Session,
    issue: Issue,
    *,
    actor_id: int | None = None,
    now: datetime | None = None,
) -> None:
    """Snapshot the key and title, then tell the reporter and the assignee."""
    actor = actor_id if actor_id is not None else acting_user_id()
    if actor is None:
        return
    _fan_out(
        session,
        issue,
        NotificationType.DELETE_ON_CREATED,
        NotificationType.DELETE_ON_ASSIGNED,
        "This issue was deleted.",
        actor_id=actor,
        now=now if now is not None else utc_now(),
        immediate=True,
    )


def dispatch_due_email(
    session: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Send email whose stored due time has passed. A miss stays for later."""
    moment = _stored(now if now is not None else utc_now())
    sent = 0
    pending = session.scalars(
        select(Notice).where(
            Notice.email.is_(True),
            Notice.email_sent_at.is_(None),
            Notice.deliver_at.is_not(None),
        ),
    ).all()
    for notice in pending:
        due = notice.deliver_at
        if due is None or _aware(due) > _aware(moment):
            continue
        if _try_email(session, notice):
            notice.email_sent_at = moment
            sent += 1
    session.flush()
    return sent


def dispatch_due_phone(
    session: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Send due phone alerts. A miss leaves the stamp empty so the next loop retries."""
    moment = now if now is not None else utc_now()
    sent = 0
    pending = session.scalars(
        select(Notice).where(
            Notice.phone.is_(True),
            Notice.phone_sent_at.is_(None),
            Notice.deliver_at.is_not(None),
        ),
    ).all()
    for notice in pending:
        due = notice.deliver_at
        if due is None or _aware(due) > _aware(moment):
            continue
        if _try_phone(session, notice):
            notice.phone_sent_at = _stored(moment)
            sent += 1
    session.flush()
    return sent


def deliver_phone_alert(session: Session, notice: Notice) -> bool:
    """Hand one notice to the configured phone provider."""
    from keel.services import phone as phone_service

    return phone_service.deliver(session, notice)


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


def _fan_out(
    session: Session,
    issue: Issue,
    created_type: NotificationType,
    assigned_type: NotificationType,
    body: str,
    *,
    actor_id: int,
    now: datetime,
    immediate: bool,
    settings: KeelSettings | None = None,
    grow: bool = False,
) -> None:
    people: dict[int, list[NotificationType]] = {}
    if issue.reporter_id is not None and issue.reporter_id != actor_id:
        people.setdefault(issue.reporter_id, []).append(created_type)
    if issue.assignee_id is not None and issue.assignee_id != actor_id:
        people.setdefault(issue.assignee_id, []).append(assigned_type)
    for user_id, types in people.items():
        _deliver(
            session,
            issue,
            user_id,
            types,
            body,
            actor_id=actor_id,
            now=now,
            immediate=immediate,
            settings=settings,
            grow=grow,
        )


def _deliver(
    session: Session,
    issue: Issue,
    recipient_id: int,
    types: Sequence[NotificationType],
    body: str,
    *,
    actor_id: int,
    now: datetime,
    immediate: bool,
    settings: KeelSettings | None = None,
    grow: bool = False,
) -> None:
    channels = _union(session, recipient_id, types)
    if channels is None:
        return
    moment = _stored(now)
    due = _due(moment, immediate=immediate, channels=channels, settings=settings)
    notice: Notice | None = None
    if grow:
        notice = _open_update(
            session,
            recipient_id,
            actor_id,
            issue.id,
            moment,
            _quiet_minutes(settings),
        )
    if notice is None:
        key, title = _snapshot(session, issue)
        actor = user_service.get_user(session, actor_id)
        notice = add_notice(
            session,
            recipient_id=recipient_id,
            notice_type=types[0],
            actor_id=actor_id,
            actor_name=actor.display_name,
            issue_id=issue.id,
            issue_key=key,
            issue_title=title,
            body=body,
            deliver_at=due,
            created_at=moment,
            email=channels.email,
            phone=channels.phone,
            bell=channels.bell,
        )
    else:
        notice.body = _merge_lines(notice.body, body)
        notice.changed_at = moment
        notice.email = channels.email
        notice.phone = channels.phone
        notice.bell = channels.bell
        notice.deliver_at = due
        notice.issue_title = issue.title
        # The due time moved, so an earlier send is not the full list.
        notice.email_sent_at = None
        notice.phone_sent_at = None
        session.flush()
    _send_if_due(session, notice, moment)


def _union(
    session: Session,
    user_id: int,
    types: Sequence[NotificationType],
) -> PreferenceChoice | None:
    email = False
    phone = False
    bell = False
    for notice_type in types:
        choice = channels_for(session, user_id, notice_type)
        email = email or choice.email
        phone = phone or choice.phone
        bell = bell or choice.bell
    if not email and not phone and not bell:
        return None
    return PreferenceChoice(type=types[0], email=email, phone=phone, bell=bell)


def _due(
    moment: datetime,
    *,
    immediate: bool,
    channels: PreferenceChoice,
    settings: KeelSettings | None,
) -> datetime | None:
    if not channels.email and not channels.phone:
        return None
    if immediate:
        return moment
    return moment + timedelta(minutes=_quiet_minutes(settings))


def _quiet_minutes(settings: KeelSettings | None) -> int:
    chosen = settings if settings is not None else get_settings()
    return max(chosen.notification_update_quiet_minutes, 0)


def _open_update(
    session: Session,
    recipient_id: int,
    actor_id: int,
    issue_id: int,
    moment: datetime,
    quiet_minutes: int,
) -> Notice | None:
    if quiet_minutes <= 0:
        return None
    cutoff = moment - timedelta(minutes=quiet_minutes)
    return session.scalars(
        select(Notice)
        .where(
            Notice.recipient_id == recipient_id,
            Notice.actor_id == actor_id,
            Notice.issue_id == issue_id,
            Notice.notice_type.in_(_UPDATE_TYPES),
            Notice.changed_at >= cutoff,
        )
        .order_by(Notice.id.desc()),
    ).first()


def _send_if_due(session: Session, notice: Notice, moment: datetime) -> None:
    due = notice.deliver_at
    if due is None or _aware(due) > _aware(moment):
        return
    changed = False
    if notice.email and notice.email_sent_at is None and _try_email(session, notice):
        notice.email_sent_at = moment
        changed = True
    if notice.phone and notice.phone_sent_at is None and _try_phone(session, notice):
        notice.phone_sent_at = moment
        changed = True
    if changed:
        session.flush()


def _try_email(session: Session, notice: Notice) -> bool:
    try:
        return _deliver_email(session, notice)
    except Exception:
        logger.exception("Notification email for notice %s was not sent.", notice.id)
        return False


def _deliver_email(session: Session, notice: Notice) -> bool:
    address = user_service.get_user(session, notice.recipient_id).email.strip()
    if not address:
        return False
    subject, body = _email_message(notice)
    return mail.send(address, subject, body)


def _email_message(notice: Notice) -> tuple[str, str]:
    key = notice.issue_key
    actor = notice.actor_name
    kind = notice.notice_type
    if kind == NotificationType.ASSIGNED.value:
        subject = f"Assigned to you: {key}"
    elif kind in _DELETE_TYPES:
        subject = f"{actor} deleted {key}"
    elif kind in _COMMENT_TYPES:
        subject = f"{actor} commented on {key}"
    else:
        subject = f"{actor} updated {key}"
    heading = f"{key} {notice.issue_title}".strip()
    text = notice.body.strip()
    body = f"{heading}\n\n{text}\n" if text else f"{heading}\n"
    return subject, body


def _try_phone(session: Session, notice: Notice) -> bool:
    try:
        return deliver_phone_alert(session, notice)
    except Exception:
        logger.exception("Phone alert for notice %s was not sent.", notice.id)
        return False


def _merge_lines(current: str, extra: str) -> str:
    lines: dict[str, str] = {}
    order: list[str] = []
    for line in (*current.splitlines(), *extra.splitlines()):
        if not line:
            continue
        field = line.split(":", 1)[0]
        if field not in lines:
            order.append(field)
        lines[field] = line
    return "\n".join(lines[field] for field in order)


def _snapshot(session: Session, issue: Issue) -> tuple[str, str]:
    from keel.services import issues as issue_service
    from keel.services import projects as project_service

    project = project_service.get_project(session, issue.project_id)
    return issue_service.issue_key(issue, project), issue.title


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
