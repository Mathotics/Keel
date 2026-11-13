from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from keel.app import create_app
from keel.db.engine import create_session_factory
from keel.db.models import Notice
from keel.db.models.user import utc_now
from keel.domain.enums import NotificationType
from keel.domain.errors import InvalidNotificationPreferenceError, NotFoundError
from keel.services import notifications as notification_service
from keel.services import users as user_service
from keel.services.notifications import PreferenceChoice
from keel.settings import KeelSettings


def _settings(
    *,
    read_days: int = 3,
    issued_days: int = 14,
) -> KeelSettings:
    return KeelSettings(
        _env_file=None,
        notification_read_retention_days=read_days,
        notification_issued_retention_days=issued_days,
    )


def _person(session: Session, name: str) -> int:
    return user_service.create_user(session, name).id


def _notice(
    session: Session,
    recipient_id: int,
    *,
    created_at: datetime | None = None,
    read_at: datetime | None = None,
    deliver_at: datetime | None = None,
    notice_type: NotificationType = NotificationType.COMMENT_ON_CREATED,
) -> Notice:
    notice = notification_service.add_notice(
        session,
        recipient_id=recipient_id,
        notice_type=notice_type,
        actor_name="Ada",
        issue_key="KEEL-1",
        issue_title="Hull",
        created_at=created_at,
        deliver_at=deliver_at,
    )
    if read_at is not None:
        notice.read_at = read_at
        session.flush()
    return notice


def _grid(**overrides: PreferenceChoice) -> list[PreferenceChoice]:
    choices = [
        PreferenceChoice(type=item, email=False, phone=False, bell=True)
        for item in NotificationType
    ]
    by_type = {choice.type: choice for choice in choices}
    by_type.update({choice.type: choice for choice in overrides.values()})
    return [by_type[item] for item in NotificationType]


def test_a_missing_preference_is_bell_only(session: Session) -> None:
    user_id = _person(session, "Ada")
    choices = notification_service.effective_preferences(session, user_id)
    assert [choice.type for choice in choices] == list(NotificationType)
    assert all(
        not choice.email and not choice.phone and choice.bell for choice in choices
    )
    one = notification_service.channels_for(
        session,
        user_id,
        NotificationType.ASSIGNED,
    )
    assert one == PreferenceChoice(
        type=NotificationType.ASSIGNED,
        email=False,
        phone=False,
        bell=True,
    )


def test_replacing_preferences_stores_only_overrides(session: Session) -> None:
    user_id = _person(session, "Ada")
    email_on = PreferenceChoice(
        type=NotificationType.ASSIGNED,
        email=True,
        phone=False,
        bell=True,
    )
    stored = notification_service.replace_preferences(
        session,
        user_id,
        _grid(assigned=email_on),
    )
    assert stored[2] == email_on
    assert (
        notification_service.channels_for(
            session,
            user_id,
            NotificationType.COMMENT_ON_CREATED,
        ).email
        is False
    )

    restored = notification_service.replace_preferences(session, user_id, _grid())
    assert all(choice.bell and not choice.email for choice in restored)
    assert (
        notification_service.channels_for(
            session,
            user_id,
            NotificationType.ASSIGNED,
        ).email
        is False
    )


def test_a_partial_preference_grid_is_refused(session: Session) -> None:
    user_id = _person(session, "Ada")
    with pytest.raises(InvalidNotificationPreferenceError):
        notification_service.replace_preferences(
            session,
            user_id,
            _grid()[:6],
        )


def test_the_earlier_retention_cap_wins(session: Session) -> None:
    user_id = _person(session, "Ada")
    now = datetime(2026, 11, 9, tzinfo=UTC)
    read_sooner = _notice(
        session,
        user_id,
        created_at=now - timedelta(days=10),
        read_at=now - timedelta(days=4),
    )
    issued_sooner = _notice(
        session,
        user_id,
        created_at=now - timedelta(days=20),
        read_at=now - timedelta(days=1),
        notice_type=NotificationType.ASSIGNED,
    )
    still_kept = _notice(
        session,
        user_id,
        created_at=now - timedelta(days=10),
        read_at=now - timedelta(days=1),
        notice_type=NotificationType.UPDATE_ON_CREATED,
    )
    removed = notification_service.purge_expired(
        session,
        _settings(),
        now=now,
    )
    assert removed == 2
    remaining = notification_service.list_notices(session, user_id)
    assert [notice.id for notice in remaining] == [still_kept.id]
    assert session.get(Notice, read_sooner.id) is None
    assert session.get(Notice, issued_sooner.id) is None


def test_zero_turns_one_retention_cap_off(session: Session) -> None:
    user_id = _person(session, "Ada")
    now = datetime(2026, 11, 9, tzinfo=UTC)
    ancient_unread = _notice(session, user_id, created_at=now - timedelta(days=100))
    read_long_ago = _notice(
        session,
        user_id,
        created_at=now - timedelta(days=1),
        read_at=now - timedelta(days=4),
        notice_type=NotificationType.ASSIGNED,
    )
    assert (
        notification_service.purge_expired(
            session,
            _settings(issued_days=0),
            now=now,
        )
        == 1
    )
    assert session.get(Notice, ancient_unread.id) is not None
    assert session.get(Notice, read_long_ago.id) is None

    both_off = _notice(
        session,
        user_id,
        created_at=now - timedelta(days=100),
        read_at=now - timedelta(days=100),
        notice_type=NotificationType.DELETE_ON_CREATED,
    )
    assert (
        notification_service.purge_expired(
            session,
            _settings(read_days=0, issued_days=0),
            now=now,
        )
        == 0
    )
    assert session.get(Notice, both_off.id) is not None


def test_a_due_time_is_not_a_retention_clock(session: Session) -> None:
    user_id = _person(session, "Ada")
    now = utc_now()
    notice = _notice(
        session,
        user_id,
        created_at=now,
        deliver_at=now - timedelta(days=2),
    )
    assert notification_service.purge_expired(session, _settings(), now=now) == 0
    kept = session.get(Notice, notice.id)
    assert kept is not None
    assert kept.deliver_at is not None


def test_marking_read_keeps_the_first_stamp(session: Session) -> None:
    user_id = _person(session, "Ada")
    notice = _notice(session, user_id)
    first = notification_service.mark_read(session, user_id, notice.id)
    again = notification_service.mark_read(session, user_id, notice.id)
    assert again.read_at == first.read_at
    other = _person(session, "Bea")
    with pytest.raises(NotFoundError):
        notification_service.mark_read(session, other, notice.id)


def test_notices_list_newest_first_for_the_recipient(session: Session) -> None:
    ada = _person(session, "Ada")
    bea = _person(session, "Bea")
    older = _notice(session, ada, created_at=datetime(2026, 11, 1, tzinfo=UTC))
    newer = _notice(
        session,
        ada,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
        notice_type=NotificationType.ASSIGNED,
    )
    _notice(session, bea, notice_type=NotificationType.DELETE_ON_ASSIGNED)
    listed = notification_service.list_notices(session, ada)
    assert [notice.id for notice in listed] == [newer.id, older.id]
    notification_service.delete_notice(session, ada, newer.id)
    remaining = notification_service.list_notices(session, ada)
    assert [notice.id for notice in remaining] == [older.id]


def test_a_restart_applies_stored_times(
    settings: KeelSettings,
    engine: Engine,
) -> None:
    factory = create_session_factory(engine)
    now = utc_now()
    with factory() as session:
        user_id = _person(session, "Ada")
        expired = _notice(session, user_id, created_at=now - timedelta(days=15))
        kept = _notice(
            session,
            user_id,
            created_at=now,
            deliver_at=now - timedelta(hours=1),
            notice_type=NotificationType.ASSIGNED,
        )
        session.commit()
        expired_id = expired.id
        kept_id = kept.id
        deliver_at = kept.deliver_at

    with TestClient(create_app(settings)):
        pass

    with factory() as session:
        assert session.get(Notice, expired_id) is None
        survivor = session.get(Notice, kept_id)
        assert survivor is not None
        assert survivor.deliver_at == deliver_at
