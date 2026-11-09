from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from keel.app import create_app
from keel.db.engine import create_session_factory
from keel.db.models import Notice
from keel.db.models.user import utc_now
from keel.domain.enums import IssueType, NotificationType
from keel.services import comments as comment_service
from keel.services import issues as issue_service
from keel.services import mail
from keel.services import notifications as notification_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.notifications import PreferenceChoice
from keel.settings import KeelSettings


def _project(session: Session) -> int:
    return project_service.create_project(session, "KEEL", "Keel").id


def _user(session: Session, name: str, *, email: str | None = None) -> int:
    address = f"{name.lower()}@example.com" if email is None else email
    return user_service.create_user(session, name, email=address).id


def _grid(*overrides: PreferenceChoice) -> list[PreferenceChoice]:
    by_type = {
        item: PreferenceChoice(type=item, email=False, phone=False, bell=True)
        for item in NotificationType
    }
    for choice in overrides:
        by_type[choice.type] = choice
    return [by_type[item] for item in NotificationType]


def _email(notice_type: NotificationType) -> PreferenceChoice:
    return PreferenceChoice(type=notice_type, email=True, phone=False, bell=True)


def _quiet(minutes: int) -> KeelSettings:
    return KeelSettings(_env_file=None, notification_update_quiet_minutes=minutes)


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []

    def send(to: str, subject: str, body: str) -> bool:
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr(mail, "send", send)
    return sent


def test_bell_only_does_not_email(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
    )
    comment_service.create_comment(session, issue.id, "A note", author_id=bea)
    assert sent == []
    notices = list(notification_service.list_notices(session, ada))
    assert len(notices) == 1
    assert notices[0].email_sent_at is None


def test_a_bundled_update_sends_one_email_with_the_full_list(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
    )
    notification_service.replace_preferences(
        session,
        ada,
        _grid(_email(NotificationType.UPDATE_ON_CREATED)),
    )
    start = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    notification_service.record_update(
        session,
        issue,
        ["status: To Do → In Progress"],
        actor_id=bea,
        now=start,
        settings=_quiet(5),
    )
    notification_service.record_update(
        session,
        issue,
        ["title: Hull → Deck"],
        actor_id=bea,
        now=start + timedelta(minutes=3),
        settings=_quiet(5),
    )
    assert sent == []
    assert (
        notification_service.dispatch_due_email(
            session,
            now=start + timedelta(minutes=7),
        )
        == 0
    )
    assert (
        notification_service.dispatch_due_email(
            session,
            now=start + timedelta(minutes=8),
        )
        == 1
    )
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "ada@example.com"
    assert subject == "Bea updated KEEL-1"
    assert "KEEL-1 Hull" in body
    assert "status: To Do → In Progress" in body
    assert "title: Hull → Deck" in body
    assert (
        notification_service.dispatch_due_email(
            session,
            now=start + timedelta(minutes=8),
        )
        == 0
    )


def test_an_edit_after_a_send_still_emails_the_full_list(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
    )
    notification_service.replace_preferences(
        session,
        ada,
        _grid(_email(NotificationType.UPDATE_ON_CREATED)),
    )
    start = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    notification_service.record_update(
        session,
        issue,
        ["status: To Do → In Progress"],
        actor_id=bea,
        now=start,
        settings=_quiet(5),
    )
    notice = notification_service.list_notices(session, ada)[0]
    notice.email_sent_at = notice.changed_at
    session.flush()
    notification_service.record_update(
        session,
        issue,
        ["title: Hull → Deck"],
        actor_id=bea,
        now=start + timedelta(minutes=2),
        settings=_quiet(5),
    )
    grown = notification_service.list_notices(session, ada)[0]
    assert grown.id == notice.id
    assert grown.email_sent_at is None
    assert (
        notification_service.dispatch_due_email(
            session,
            now=start + timedelta(minutes=7),
        )
        == 1
    )
    assert len(sent) == 1
    assert "status: To Do → In Progress" in sent[0][2]
    assert "title: Hull → Deck" in sent[0][2]


def test_a_zero_quiet_period_emails_each_edit(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
    )
    notification_service.replace_preferences(
        session,
        ada,
        _grid(_email(NotificationType.UPDATE_ON_CREATED)),
    )
    start = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    notification_service.record_update(
        session,
        issue,
        ["status: To Do → In Progress"],
        actor_id=bea,
        now=start,
        settings=_quiet(0),
    )
    notification_service.record_update(
        session,
        issue,
        ["title: Hull → Deck"],
        actor_id=bea,
        now=start + timedelta(seconds=1),
        settings=_quiet(0),
    )
    assert len(sent) == 2
    assert "status: To Do → In Progress" in sent[0][2]
    assert "title:" not in sent[0][2]
    assert "title: Hull → Deck" in sent[1][2]
    assert "status:" not in sent[1][2]
    assert notification_service.dispatch_due_email(session, now=start) == 0


def test_comment_assignment_and_deletion_email_immediately(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    cara = _user(session, "Cara")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
        assignee_id=cara,
    )
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            _email(NotificationType.COMMENT_ON_CREATED),
            _email(NotificationType.DELETE_ON_CREATED),
        ),
    )
    notification_service.replace_preferences(
        session,
        cara,
        _grid(
            _email(NotificationType.ASSIGNED),
            _email(NotificationType.DELETE_ON_ASSIGNED),
        ),
    )
    notification_service.record_comment(session, issue, "A note", actor_id=bea)
    notification_service.record_assignment(session, issue, actor_id=bea)
    notification_service.record_delete(session, issue, actor_id=bea)
    assert [item[0] for item in sent] == [
        "ada@example.com",
        "cara@example.com",
        "ada@example.com",
        "cara@example.com",
    ]
    assert [item[1] for item in sent] == [
        "Bea commented on KEEL-1",
        "Assigned to you: KEEL-1",
        "Bea deleted KEEL-1",
        "Bea deleted KEEL-1",
    ]
    assert "A note" in sent[0][2]
    assert "Assigned to you." in sent[1][2]
    assert "This issue was deleted." in sent[2][2]
    assert notification_service.dispatch_due_email(session) == 0


def test_a_failed_send_keeps_the_notice_and_the_comment(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_to: str, _subject: str, _body: str) -> bool:
        raise RuntimeError("down")

    monkeypatch.setattr(mail, "send", boom)
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
    )
    notification_service.replace_preferences(
        session,
        ada,
        _grid(_email(NotificationType.COMMENT_ON_CREATED)),
    )
    comment_service.create_comment(session, issue.id, "A note", author_id=bea)
    notice = notification_service.list_notices(session, ada)[0]
    assert notice.body == "A note"
    assert notice.email_sent_at is None
    sent = _capture(monkeypatch)
    assert notification_service.dispatch_due_email(session) == 1
    assert sent[0][0] == "ada@example.com"
    assert notice.email_sent_at is not None


def test_unset_smtp_keeps_the_notice(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mail,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host="",
            smtp_port=587,
            smtp_username="",
            smtp_password="",
            smtp_from="",
            smtp_starttls=True,
        ),
    )
    project_id = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = issue_service.create_issue(
        session,
        project_id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=ada,
    )
    notification_service.replace_preferences(
        session,
        ada,
        _grid(_email(NotificationType.COMMENT_ON_CREATED)),
    )
    comment_service.create_comment(session, issue.id, "A note", author_id=bea)
    notice = notification_service.list_notices(session, ada)[0]
    assert notice.email_sent_at is None
    sent = _capture(monkeypatch)
    assert notification_service.dispatch_due_email(session) == 1
    assert len(sent) == 1


def test_a_missing_address_is_left_unsent(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    ada = user_service.create_user(session, "Ada").id
    notification_service.add_notice(
        session,
        recipient_id=ada,
        notice_type=NotificationType.COMMENT_ON_CREATED,
        actor_name="Bea",
        issue_key="KEEL-1",
        issue_title="Hull",
        body="A note",
        email=True,
        deliver_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
    )
    assert (
        notification_service.dispatch_due_email(
            session,
            now=datetime(2026, 11, 9, 12, 1, tzinfo=UTC),
        )
        == 0
    )
    assert sent == []
    notice = notification_service.list_notices(session, ada)[0]
    assert notice.email_sent_at is None


def test_a_restart_sends_email_whose_due_time_has_passed(
    settings: KeelSettings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    factory = create_session_factory(engine)
    now = utc_now()
    with factory() as session:
        ada = _user(session, "Ada")
        due = notification_service.add_notice(
            session,
            recipient_id=ada,
            notice_type=NotificationType.UPDATE_ON_CREATED,
            actor_name="Bea",
            issue_key="KEEL-1",
            issue_title="Hull",
            body="status: To Do → In Progress\ntitle: Hull → Deck",
            email=True,
            deliver_at=now - timedelta(minutes=1),
            created_at=now - timedelta(minutes=6),
        )
        waiting = notification_service.add_notice(
            session,
            recipient_id=ada,
            notice_type=NotificationType.COMMENT_ON_CREATED,
            actor_name="Bea",
            issue_key="KEEL-1",
            issue_title="Hull",
            body="Later",
            email=True,
            deliver_at=now + timedelta(hours=1),
            created_at=now,
        )
        session.commit()
        due_id = due.id
        waiting_id = waiting.id

    with TestClient(create_app(settings)):
        pass

    assert len(sent) == 1
    assert sent[0][0] == "ada@example.com"
    assert sent[0][1] == "Bea updated KEEL-1"
    assert "status: To Do → In Progress" in sent[0][2]
    assert "title: Hull → Deck" in sent[0][2]
    with factory() as session:
        delivered = session.get(Notice, due_id)
        held = session.get(Notice, waiting_id)
        assert delivered is not None and delivered.email_sent_at is not None
        assert held is not None and held.email_sent_at is None
