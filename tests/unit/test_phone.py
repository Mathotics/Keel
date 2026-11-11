import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Notice, Project
from keel.db.models.phone_device import PhoneDevice
from keel.domain.enums import IssueType, NotificationType
from keel.services import issues as issue_service
from keel.services import notifications as notification_service
from keel.services import phone as phone_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.notifications import PreferenceChoice
from keel.settings import KeelSettings


def _project(session: Session) -> Project:
    return project_service.create_project(session, "KEEL", "Keel")


def _user(session: Session, name: str) -> int:
    return user_service.create_user(session, name).id


def _issue(session: Session, project: Project, reporter_id: int) -> Issue:
    return issue_service.create_issue(
        session,
        project.id,
        type=IssueType.STORY,
        title="Hull",
        reporter_id=reporter_id,
    )


def _grid(*overrides: PreferenceChoice) -> list[PreferenceChoice]:
    by_type = {
        item: PreferenceChoice(type=item, email=False, phone=False, bell=True)
        for item in NotificationType
    }
    for choice in overrides:
        by_type[choice.type] = choice
    return [by_type[item] for item in NotificationType]


def _use(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    phone_service._access.clear()
    phone_service._warned = False
    chosen = {
        "push_provider": "",
        "fcm_credentials_file": "",
        "ntfy_base_url": "",
        "ntfy_token": "",
    }
    chosen.update(values)
    settings = KeelSettings(
        _env_file=None,
        push_provider=chosen["push_provider"],
        fcm_credentials_file=chosen["fcm_credentials_file"],
        ntfy_base_url=chosen["ntfy_base_url"],
        ntfy_token=chosen["ntfy_token"],
    )
    monkeypatch.setattr(phone_service, "get_settings", lambda: settings)


def _notice(
    session: Session,
    recipient_id: int,
    *,
    phone: bool = True,
    deliver_at: datetime | None = None,
    issue_id: int | None = None,
    kind: NotificationType = NotificationType.COMMENT_ON_CREATED,
) -> Notice:
    return notification_service.add_notice(
        session,
        recipient_id=recipient_id,
        notice_type=kind,
        actor_name="Ada",
        issue_id=issue_id,
        issue_key="KEEL-1",
        issue_title="Hull",
        body="Plating",
        phone=phone,
        deliver_at=deliver_at,
    )


def _credentials(tmp_path: Path) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    path = tmp_path / "firebase.json"
    path.write_text(
        json.dumps(
            {
                "client_email": "push@keel.iam.gserviceaccount.com",
                "private_key": pem,
                "project_id": "keel-push",
            },
        ),
        encoding="utf-8",
    )
    return str(path)


def test_an_unset_provider_leaves_the_alert_to_retry(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch)
    ada = _user(session, "Ada")
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    _notice(session, ada, deliver_at=now)
    calls: list[str] = []

    def post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        calls.append(url)
        return 200, ""

    monkeypatch.setattr(phone_service, "_post", post)
    assert notification_service.dispatch_due_phone(session, now=now) == 0
    assert calls == []
    stored = notification_service.list_notices(session, ada)
    assert stored[0].phone_sent_at is None


def test_ntfy_sends_one_alert_and_a_quiet_bundle_waits(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, push_provider="ntfy", ntfy_base_url="http://ntfy.local")
    project = _project(session)
    ada = _user(session, "Ada")
    bea = _user(session, "Bea")
    issue = _issue(session, project, ada)
    notification_service.replace_preferences(
        session,
        ada,
        _grid(
            PreferenceChoice(
                type=NotificationType.UPDATE_ON_CREATED,
                email=False,
                phone=True,
                bell=True,
            ),
        ),
    )
    calls: list[tuple[str, bytes, dict[str, str]]] = []

    def post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        calls.append((url, data, headers))
        return 200, ""

    monkeypatch.setattr(phone_service, "_post", post)
    start = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    quiet = KeelSettings(_env_file=None, notification_update_quiet_minutes=5)
    notification_service.record_update(
        session,
        issue,
        ["status: To Do → In Progress"],
        actor_id=bea,
        now=start,
        settings=quiet,
    )
    notification_service.record_update(
        session,
        issue,
        ["title: Hull → Deck"],
        actor_id=bea,
        now=start + timedelta(minutes=2),
        settings=quiet,
    )
    assert calls == []
    sent = notification_service.dispatch_due_phone(
        session,
        now=start + timedelta(minutes=7),
    )
    assert sent == 1
    assert len(calls) == 1
    url, body, headers = calls[0]
    assert url.startswith("http://ntfy.local/")
    assert "Plating" not in body.decode()
    assert b"status: To Do" in body
    assert b"title: Hull" in body
    assert headers["Title"] == "Bea updated KEEL-1"
    assert (
        notification_service.dispatch_due_phone(
            session,
            now=start + timedelta(minutes=8),
        )
        == 0
    )
    assert len(calls) == 1
    provider, subscribe = phone_service.setup(session, ada)
    assert provider == "ntfy"
    assert subscribe == url


def test_a_phone_channel_that_is_off_stays_quiet(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, push_provider="ntfy", ntfy_base_url="https://ntfy.example")
    ada = _user(session, "Ada")
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    _notice(session, ada, phone=False, deliver_at=now)
    calls: list[str] = []

    def post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        calls.append(url)
        return 200, ""

    monkeypatch.setattr(phone_service, "_post", post)
    assert notification_service.dispatch_due_phone(session, now=now) == 0
    assert calls == []


def test_an_ntfy_failure_does_not_stamp_the_notice(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(
        monkeypatch,
        push_provider="ntfy",
        ntfy_base_url="http://ntfy.local",
        ntfy_token="secret",
    )
    ada = _user(session, "Ada")
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    _notice(session, ada, deliver_at=now, kind=NotificationType.ASSIGNED)
    seen: dict[str, str] = {}

    def post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        seen.update(headers)
        return 503, "down"

    monkeypatch.setattr(phone_service, "_post", post)
    assert notification_service.dispatch_due_phone(session, now=now) == 0
    assert seen["Authorization"] == "Bearer secret"
    assert seen["Title"] == "Assigned to you: KEEL-1"
    assert notification_service.list_notices(session, ada)[0].phone_sent_at is None


def test_firebase_sends_once_per_registered_phone(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use(
        monkeypatch,
        push_provider="fcm",
        fcm_credentials_file=_credentials(tmp_path),
    )
    ada = _user(session, "Ada")
    issue = _issue(session, _project(session), ada)
    phone_service.register_token(session, ada, "phone-a")
    phone_service.register_token(session, ada, "phone-b")
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    _notice(session, ada, deliver_at=now, issue_id=issue.id)
    calls: list[tuple[str, bytes]] = []

    def post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        calls.append((url, data))
        if url.endswith("/token"):
            return 200, json.dumps({"access_token": "ya29.test", "expires_in": 3600})
        return 200, "{}"

    monkeypatch.setattr(phone_service, "_post", post)
    assert notification_service.dispatch_due_phone(session, now=now) == 1
    assert notification_service.dispatch_due_phone(session, now=now) == 0
    token_calls = [url for url, _data in calls if url.endswith("/token")]
    sends = [data for url, data in calls if url.endswith("/messages:send")]
    assert token_calls == ["https://oauth2.googleapis.com/token"]
    assert len(sends) == 2
    tokens = {json.loads(raw)["message"]["token"] for raw in sends}
    assert tokens == {"phone-a", "phone-b"}
    message = json.loads(sends[0])["message"]
    assert message["data"]["issueId"] == str(issue.id)
    assert message["android"]["notification"]["channel_id"] == "keel-alerts"
    assert message["notification"]["title"] == "Ada commented on KEEL-1"
    provider, url = phone_service.setup(session, ada)
    assert provider == "fcm"
    assert url is None


def test_a_stale_firebase_token_is_dropped(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use(
        monkeypatch,
        push_provider="fcm",
        fcm_credentials_file=_credentials(tmp_path),
    )
    ada = _user(session, "Ada")
    phone_service.register_token(session, ada, "gone")
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    _notice(session, ada, deliver_at=now, issue_id=None)

    def post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
        if url.endswith("/token"):
            return 200, json.dumps({"access_token": "ya29.test", "expires_in": 3600})
        return 404, "UNREGISTERED"

    monkeypatch.setattr(phone_service, "_post", post)
    assert notification_service.dispatch_due_phone(session, now=now) == 0
    gone = session.scalar(select(PhoneDevice).where(PhoneDevice.token == "gone"))
    assert gone is None


def test_describe_names_the_configured_provider() -> None:
    assert "ntfy app" in phone_service.describe("ntfy", "http://ntfy.local/topic")
    assert "Firebase" in phone_service.describe("fcm", None)
    assert "until a provider" in phone_service.describe("", None)
