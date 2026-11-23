import pytest
from fastapi.testclient import TestClient

from tests.integration.test_issues_api import create_issue


@pytest.fixture
def project_id(client: TestClient) -> int:
    response = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    return int(response.json()["id"])


def test_a_new_person_has_no_reminder_until_they_save_one(
    client: TestClient,
    project_id: int,
) -> None:
    assert client.get("/api/v1/profile/reminders").json() == {"rule": None}
    issue = create_issue(
        client,
        project_id,
        title="File taxes",
        due_at="2099-06-01T17:00:00",
    )

    saved = client.put(
        "/api/v1/profile/reminders",
        json={
            "due_offsets": [{"amount": 1, "unit": "hour"}],
            "at_due": True,
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["scope"] == "default"
    assert body["due_offsets"] == [{"amount": 1, "unit": "hour"}]

    schedule = client.get("/api/v1/reminders/schedule?catch_up=false")
    assert schedule.status_code == 200, schedule.text
    matched = [row for row in schedule.json() if row["issue_id"] == issue["id"]]
    assert [row["at"] for row in matched] == [
        "2099-06-01T16:00:00",
        "2099-06-01T17:00:00",
    ]
    assert matched[0]["reasons"] == ["Due in 1 hour"]
    assert matched[0]["issue_key"] == issue["key"]


def test_an_issue_rule_replaces_the_default_and_reset_restores_it(
    client: TestClient,
    project_id: int,
) -> None:
    client.put(
        "/api/v1/profile/reminders",
        json={"at_due": True},
    )
    issue = create_issue(
        client,
        project_id,
        title="Own reminder",
        due_at="2099-06-02T12:00:00",
    )
    saved = client.put(
        f"/api/v1/issues/{issue['id']}/reminder",
        json={"at_start": True},
    )
    assert saved.status_code == 200, saved.text
    effective = client.get(f"/api/v1/issues/{issue['id']}/reminder")
    assert effective.json()["source"] == "issue"
    assert effective.json()["due_missing"] is False
    assert effective.json()["start_missing"] is True

    stale = client.put(
        f"/api/v1/issues/{issue['id']}/reminder",
        json={"at_due": True, "base_updated_at": "2000-01-01T00:00:00"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "reminder.conflict"

    removed = client.delete(
        f"/api/v1/issues/{issue['id']}/reminder",
        params={"base_updated_at": saved.json()["updated_at"]},
    )
    assert removed.status_code == 204, removed.text
    restored = client.get(f"/api/v1/issues/{issue['id']}/reminder")
    assert restored.json()["source"] == "default"
    assert restored.json()["rule"]["at_due"] is True


def test_snooze_and_dismiss_belong_to_the_issue(
    client: TestClient,
    project_id: int,
) -> None:
    issue = create_issue(
        client,
        project_id,
        title="Late",
        due_at="2000-01-01T09:00:00",
    )
    client.put(
        f"/api/v1/issues/{issue['id']}/reminder",
        json={
            "at_due": True,
            "overdue": {"kind": "every_n", "amount": 1, "unit": "day"},
        },
    )
    snoozed = client.put(
        f"/api/v1/issues/{issue['id']}/reminder/snooze",
        json={"until": "2099-01-01T09:00:00"},
    )
    assert snoozed.status_code == 200, snoozed.text
    schedule = client.get("/api/v1/reminders/schedule?catch_up=true").json()
    overdue = [
        row
        for row in schedule
        if row["issue_id"] == issue["id"] and "Overdue" in row["reasons"]
    ]
    assert overdue
    assert overdue[0]["at"].startswith("2099-01-01T09:00:00")

    dismissed = client.post(
        f"/api/v1/issues/{issue['id']}/reminder/dismiss-overdue",
        json={"base_updated_at": snoozed.json()["updated_at"]},
    )
    assert dismissed.status_code == 200, dismissed.text
    after = client.get("/api/v1/reminders/schedule?catch_up=true").json()
    assert [
        row
        for row in after
        if row["issue_id"] == issue["id"] and "Overdue" in row["reasons"]
    ] == []


def test_the_profile_form_saves_a_default(client: TestClient) -> None:
    response = client.post(
        "/web/profile/reminders",
        data={
            "due_amount": "2",
            "due_unit": "day",
            "at_due": "1",
            "overdue_kind": "daily_at",
            "overdue_clock": "09:00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    page = client.get("/profile")
    assert page.status_code == 200
    assert 'value="2"' in page.text
    assert "09:00" in page.text
    stored = client.get("/api/v1/profile/reminders").json()["rule"]
    assert stored["due_offsets"] == [{"amount": 2, "unit": "day"}]
    assert stored["overdue"] == {
        "kind": "daily_at",
        "amount": None,
        "unit": None,
        "minute_of_day": 540,
    }
