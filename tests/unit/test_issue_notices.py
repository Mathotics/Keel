from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from keel.db.models import Issue, Notice, Project
from keel.domain.enums import IssueStatus, IssueType, NotificationType
from keel.services import comments as comment_service
from keel.services import issues as issue_service
from keel.services import notifications as notification_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.identity import bind_acting_user, reset_acting_user
from keel.services.notifications import PreferenceChoice
from keel.settings import KeelSettings


def _project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _user(session: Session, name: str) -> int:
    return user_service.create_user(session, name).id


def _issue(
    session: Session,
    project: Project,
    *,
    reporter_id: int,
    assignee_id: int | None = None,
    title: str = "Hull",
) -> Issue:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title=title,
        reporter_id=reporter_id,
        assignee_id=assignee_id,
    )


def _grid(*overrides: PreferenceChoice) -> list[PreferenceChoice]:
    by_type = {
        item: PreferenceChoice(type=item, email=False, phone=False, bell=True)
        for item in NotificationType
    }
    for choice in overrides:
        by_type[choice.type] = choice
    return [by_type[item] for item in NotificationType]


def _quiet(minutes: int) -> KeelSettings:
    return KeelSettings(_env_file=None, notification_update_quiet_minutes=minutes)


def test_the_actor_is_skipped(session: Session) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada, assignee_id=bea)
    token = bind_acting_user(user_service.get_user(session, ada))
    try:
        comment_service.create_comment(session, issue.id, "A note", author_id=ada)
    finally:
        reset_acting_user(token)
    ada_notices = notification_service.list_notices(session, ada)
    bea_notices = notification_service.list_notices(session, bea)
    assert list(ada_notices) == []
    assert len(bea_notices) == 1
    assert bea_notices[0].notice_type == NotificationType.COMMENT_ON_ASSIGNED.value


def test_both_roles_produce_one_notice_with_unioned_channels(session: Session) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada, assignee_id=ada)
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            PreferenceChoice(
                type=NotificationType.COMMENT_ON_CREATED,
                email=True,
                phone=False,
                bell=False,
            ),
            PreferenceChoice(
                type=NotificationType.COMMENT_ON_ASSIGNED,
                email=False,
                phone=True,
                bell=False,
            ),
        ),
    )
    comment_service.create_comment(session, issue.id, "A note", author_id=bea)
    notices = list(notification_service.list_notices(session, ada))
    assert len(notices) == 1
    assert notices[0].email is True
    assert notices[0].phone is True
    assert notices[0].bell is False
    assert notices[0].deliver_at is not None


def test_field_edits_inside_the_quiet_period_grow_one_notice(session: Session) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada)
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            PreferenceChoice(
                type=NotificationType.UPDATE_ON_CREATED,
                email=True,
                phone=False,
                bell=True,
            ),
        ),
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
        ["title: Hull → Deck", "status: To Do → Done"],
        actor_id=bea,
        now=start + timedelta(minutes=2),
        settings=_quiet(5),
    )
    notices = list(notification_service.list_notices(session, ada))
    assert len(notices) == 1
    assert notices[0].body.splitlines() == [
        "status: To Do → Done",
        "title: Hull → Deck",
    ]
    assert notices[0].deliver_at == datetime(2026, 11, 9, 12, 7)


def test_a_zero_quiet_period_sends_each_edit_on_its_own(session: Session) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada)
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            PreferenceChoice(
                type=NotificationType.UPDATE_ON_CREATED,
                email=True,
                phone=False,
                bell=True,
            ),
        ),
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
    notices = list(notification_service.list_notices(session, ada))
    assert len(notices) == 2
    assert {notice.deliver_at for notice in notices} == {
        datetime(2026, 11, 9, 12, 0),
        datetime(2026, 11, 9, 12, 0, 1),
    }


def test_comments_assignment_and_deletion_stay_separate_and_immediate(
    session: Session,
) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    cara = _user(session, "Cara")
    issue = _issue(session, project, reporter_id=ada, assignee_id=bea)
    emailed = {"email": True, "phone": False, "bell": True}
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            PreferenceChoice(type=NotificationType.COMMENT_ON_CREATED, **emailed),
            PreferenceChoice(type=NotificationType.UPDATE_ON_CREATED, **emailed),
            PreferenceChoice(type=NotificationType.DELETE_ON_CREATED, **emailed),
        ),
    )
    notification_service.replace_preferences(
        session,
        bea,
        _grid(
            PreferenceChoice(type=NotificationType.COMMENT_ON_ASSIGNED, **emailed),
        ),
    )
    notification_service.replace_preferences(
        session,
        cara,
        _grid(PreferenceChoice(type=NotificationType.ASSIGNED, **emailed)),
    )
    token = bind_acting_user(user_service.get_user(session, bea))
    try:
        comment_service.create_comment(session, issue.id, "A note", author_id=bea)
        issue_service.update_issue(
            session,
            issue.id,
            status=IssueStatus.IN_PROGRESS,
            assignee_id=cara,
            actor_name="Bea",
        )
        issue_service.delete_issue(session, issue.id)
    finally:
        reset_acting_user(token)
    session.expire_all()

    ada_notices = list(notification_service.list_notices(session, ada))
    assert [notice.notice_type for notice in ada_notices] == [
        NotificationType.DELETE_ON_CREATED.value,
        NotificationType.UPDATE_ON_CREATED.value,
        NotificationType.COMMENT_ON_CREATED.value,
    ]
    update = next(
        notice
        for notice in ada_notices
        if notice.notice_type == NotificationType.UPDATE_ON_CREATED.value
    )
    comment = next(
        notice
        for notice in ada_notices
        if notice.notice_type == NotificationType.COMMENT_ON_CREATED.value
    )
    deleted = next(
        notice
        for notice in ada_notices
        if notice.notice_type == NotificationType.DELETE_ON_CREATED.value
    )
    assert "status:" in update.body
    assert "assignee" not in update.body
    update_due = update.deliver_at
    comment_due = comment.deliver_at
    deleted_due = deleted.deliver_at
    assert update_due is not None
    assert comment_due is not None
    assert deleted_due is not None
    assert update_due > comment_due
    assert comment_due == comment.created_at
    assert deleted_due == deleted.created_at
    assert deleted.issue_id is None
    assert deleted.issue_key == "KEEL-1"
    assert deleted.issue_title == "Hull"

    cara_notices = list(notification_service.list_notices(session, cara))
    assigned = next(
        notice
        for notice in cara_notices
        if notice.notice_type == NotificationType.ASSIGNED.value
    )
    assert assigned.body == "Assigned to you."
    assert assigned.deliver_at == assigned.created_at
    assert NotificationType.DELETE_ON_ASSIGNED.value in {
        notice.notice_type for notice in cara_notices
    }


def test_unassign_and_comment_removal_stay_quiet(session: Session) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada, assignee_id=bea)
    token = bind_acting_user(user_service.get_user(session, ada))
    try:
        comment = comment_service.create_comment(
            session,
            issue.id,
            "A note",
            author_id=ada,
        )
        comment_service.delete_comment(session, comment.id)
        issue_service.update_issue(
            session,
            issue.id,
            assignee_id=None,
            actor_name="Ada",
        )
    finally:
        reset_acting_user(token)
    bea_notices = list(notification_service.list_notices(session, bea))
    assert len(bea_notices) == 1
    assert bea_notices[0].notice_type == NotificationType.COMMENT_ON_ASSIGNED.value
    assert list(notification_service.list_notices(session, ada)) == []


def test_a_phone_failure_does_not_fail_the_save(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada)

    def boom(_notice: Notice) -> None:
        raise RuntimeError("down")

    monkeypatch.setattr(notification_service, "deliver_phone_alert", boom)
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            PreferenceChoice(
                type=NotificationType.COMMENT_ON_CREATED,
                email=False,
                phone=True,
                bell=True,
            ),
        ),
    )
    comment_service.create_comment(session, issue.id, "A note", author_id=bea)
    notices = list(notification_service.list_notices(session, ada))
    assert len(notices) == 1
    assert notices[0].phone_sent_at is None


def test_a_due_phone_alert_waits_until_a_provider_is_configured(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel.services import phone as phone_service

    monkeypatch.setattr(
        phone_service,
        "get_settings",
        lambda: KeelSettings(_env_file=None),
    )
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, reporter_id=ada)
    now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    notification_service.add_notice(
        session,
        recipient_id=ada,
        notice_type=NotificationType.UPDATE_ON_CREATED,
        actor_id=bea,
        actor_name="Bea",
        issue_id=issue.id,
        issue_key="KEEL-1",
        issue_title="Hull",
        phone=True,
        deliver_at=now - timedelta(minutes=1),
        created_at=now - timedelta(minutes=6),
    )
    waiting = notification_service.add_notice(
        session,
        recipient_id=ada,
        notice_type=NotificationType.COMMENT_ON_CREATED,
        actor_id=bea,
        actor_name="Bea",
        issue_id=issue.id,
        issue_key="KEEL-1",
        issue_title="Hull",
        phone=True,
        deliver_at=now + timedelta(minutes=5),
        created_at=now,
    )
    assert notification_service.dispatch_due_phone(session, now=now) == 0
    due = session.get(Notice, waiting.id)
    sent = notification_service.list_notices(session, ada)
    assert due is not None
    assert due.phone_sent_at is None
    assert all(notice.phone_sent_at is None for notice in sent)
