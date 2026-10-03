import re
from calendar import monthrange
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD

Json = dict[str, Any]


def _tester(client: TestClient) -> Json:
    return next(
        user
        for user in client.get("/api/v1/users").json()
        if user["display_name"] == "Tester"
    )


def test_home_is_a_page_not_a_redirect(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "Nothing assigned to you right now." in response.text
    assert 'href="/projects"' in response.text
    assert "Create a project" in response.text
    assert "Assigned to me" not in response.text
    assert "New project" not in response.text


def test_quiet_home_with_projects_does_not_link_as_if_none_exist(
    client: TestClient,
) -> None:
    client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    page = client.get("/")
    assert page.status_code == 200
    assert "Nothing assigned to you right now." in page.text
    assert "Create a project" not in page.text
    assert "Assigned to me" not in page.text


def test_home_lists_assigned_work_and_hides_unassigned(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Mine",
            "assignee_id": tester["id"],
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Unowned"},
    )

    page = client.get("/")
    assert page.status_code == 200
    assert "Assigned to me" in page.text
    assert "KEEL-1" in page.text
    assert "Mine" in page.text
    assert 'data-type="story"' in page.text
    assert "keel-chip keel-type" in page.text
    assert "Unowned" not in page.text
    assert "Nothing assigned to you right now." not in page.text
    assert "<h2>Blocked</h2>" not in page.text


def test_the_same_issue_can_appear_in_more_than_one_section(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Late",
            "assignee_id": tester["id"],
            "due_at": "2020-01-01T09:00:00",
            "status": "blocked",
        },
    )

    page = client.get("/")
    assigned = page.text.split("<h2>Assigned to me</h2>", 1)[1].split("<h2>", 1)[0]
    due = page.text.split("<h2>Due or overdue</h2>", 1)[1].split("<h2>", 1)[0]
    blocked = page.text.split("<h2>Blocked</h2>", 1)[1]
    assert "KEEL-1" in assigned
    assert "KEEL-1" in due
    assert "KEEL-1" in blocked


def test_home_lists_due_and_starting_before_assigned(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Late and begun",
            "assignee_id": tester["id"],
            "due_at": "2020-01-01T09:00:00",
            "start_at": "2020-01-01T08:00:00",
            "status": "blocked",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Just mine",
            "assignee_id": tester["id"],
        },
    )

    page = client.get("/")
    headings = re.findall(r"<h2>([^<]+)</h2>", page.text)
    assert headings[:3] == [
        "Due or overdue",
        "Starting or started",
        "Assigned to me",
    ]
    assert headings[3] == "Blocked"


def _look_ahead(day: date) -> tuple[str, str] | None:
    """Panel key and heading for tomorrow, when it is still this week or month."""
    soon = day + timedelta(days=1)
    week_end = day + timedelta(days=7)
    month_end = date(day.year, day.month, monthrange(day.year, day.month)[1])
    if soon <= week_end:
        return "week", "Due this week"
    if soon <= month_end:
        return "month", "Due this month"
    return None


def test_home_lists_look_ahead_due_after_due_or_overdue(client: TestClient) -> None:
    today = date.today()
    panel = _look_ahead(today)
    if panel is None:
        pytest.skip("no look-ahead days remain in this week or month")
    key, heading = panel
    soon = today + timedelta(days=1)
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Late",
            "assignee_id": tester["id"],
            "due_at": "2020-01-01T09:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Soon",
            "assignee_id": tester["id"],
            "due_at": f"{soon.isoformat()}T09:00:00",
        },
    )

    page = client.get("/")
    headings = re.findall(r"<h2>([^<]+)</h2>", page.text)
    assert headings[:3] == [
        "Due or overdue",
        heading,
        "Assigned to me",
    ]
    look_ahead = page.text.split(f"<h2>{heading}</h2>", 1)[1].split("<h2>", 1)[0]
    due = page.text.split("<h2>Due or overdue</h2>", 1)[1].split("<h2>", 1)[0]
    assert "Soon" in look_ahead
    assert "Late" not in look_ahead
    assert "Late" in due
    assert "Soon" not in due
    assert f'data-keel-inbox-panel="{key}"' in page.text
    assert "Due this week or this month" not in page.text


def test_the_inbox_cookie_closes_the_look_ahead_panel(client: TestClient) -> None:
    today = date.today()
    panel = _look_ahead(today)
    if panel is None:
        pytest.skip("no look-ahead days remain in this week or month")
    key, heading = panel
    soon = today + timedelta(days=1)
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Soon",
            "assignee_id": tester["id"],
            "due_at": f"{soon.isoformat()}T09:00:00",
        },
    )
    client.cookies.set("keel_inbox", key)
    page = client.get("/")
    look_ahead = _panel(page.text, key)
    assert " open" not in look_ahead
    assert f"<h2>{heading}</h2>" in page.text
    assert "Soon" in page.text


def test_home_lists_starting_or_started(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Begun",
            "assignee_id": tester["id"],
            "start_at": "2020-01-01T09:00:00",
        },
    )

    page = client.get("/")
    assert "<h2>Starting or started</h2>" in page.text
    starting = page.text.split("<h2>Starting or started</h2>", 1)[1]
    assert "KEEL-1" in starting


def test_status_from_home_returns_to_home(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Ready",
            "assignee_id": tester["id"],
        },
    ).json()

    response = client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    page = client.get("/")
    assert "In Progress" in page.text
    assert "data-keel-autosubmit" in page.text
    assert ">Move<" in page.text


def test_switching_the_picker_changes_whose_inbox_is_shown(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada", "password": TEST_PASSWORD},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "For Tester",
            "assignee_id": tester["id"],
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "For Ada",
            "assignee_id": ada["id"],
        },
    )

    as_tester = client.get("/")
    assert "For Tester" in as_tester.text
    assert "For Ada" not in as_tester.text

    client.post(
        "/login",
        data={"username": "Ada", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    as_ada = client.get("/")
    assert "For Ada" in as_ada.text
    assert "For Tester" not in as_ada.text


def _panel(html: str, key: str) -> str:
    marker = f'data-keel-inbox-panel="{key}"'
    start = html.index("<details")
    while start != -1:
        end = html.index(">", start)
        tag = html[start : end + 1]
        if marker in tag:
            return tag
        start = html.find("<details", end)
    raise AssertionError(f"no inbox panel {key}")


def _seed_assigned(client: TestClient) -> dict[str, Any]:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Mine",
            "assignee_id": tester["id"],
        },
    ).json()
    assert isinstance(issue, dict)
    return issue


def test_home_sections_are_open_disclosures_with_a_count(client: TestClient) -> None:
    _seed_assigned(client)
    page = client.get("/")
    assigned = _panel(page.text, "assigned")
    assert " open" in assigned
    assert "<h2>Assigned to me</h2>" in page.text
    assert "keel-inbox__count" in page.text
    assert ">1<" in page.text.split("keel-inbox__count", 1)[1][:40]
    assert "Minimize" in page.text
    assert 'src="/assets/js/inbox.js"' in page.text
    assert 'action="/web/inbox"' in page.text


def test_the_inbox_cookie_closes_a_section_and_keeps_the_heading(
    client: TestClient,
) -> None:
    _seed_assigned(client)
    client.cookies.set("keel_inbox", "assigned.nope")
    page = client.get("/")
    assigned = _panel(page.text, "assigned")
    assert " open" not in assigned
    assert "<h2>Assigned to me</h2>" in page.text
    assert "KEEL-1" in page.text
    assert "Expand" in page.text
    assert "Minimize" not in page.text


def test_minimizing_a_home_section_sets_the_cookie_and_returns(
    client: TestClient,
) -> None:
    _seed_assigned(client)
    response = client.post(
        "/web/inbox",
        data={"collapsed": "assigned", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.cookies["keel_inbox"] == "assigned"
    page = client.get("/")
    assert " open" not in _panel(page.text, "assigned")


def test_home_lists_completed_today_last(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Shipped",
            "assignee_id": tester["id"],
        },
    ).json()
    client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "done"})

    page = client.get("/")
    headings = re.findall(r"<h2>([^<]+)</h2>", page.text)
    assert headings[-1] == "Completed today"
    assert "<h2>Assigned to me</h2>" not in page.text
    assert "Nothing assigned to you right now." not in page.text
    completed = page.text.split("<h2>Completed today</h2>", 1)[1]
    assert "KEEL-1" in completed
    assert "Shipped" in completed
    assert ">Completed<" in completed
    assert 'data-keel-inbox-panel="completed"' in page.text


def test_cancelled_stays_off_completed_today(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Dropped",
            "assignee_id": tester["id"],
        },
    ).json()
    client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "cancelled"})

    page = client.get("/")
    assert "<h2>Completed today</h2>" not in page.text
    assert "Dropped" not in page.text


def test_the_inbox_cookie_closes_completed_today(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Shipped",
            "assignee_id": tester["id"],
        },
    ).json()
    client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "done"})
    client.cookies.set("keel_inbox", "completed")
    page = client.get("/")
    completed = _panel(page.text, "completed")
    assert " open" not in completed
    assert "<h2>Completed today</h2>" in page.text
    assert "KEEL-1" in page.text


def test_status_from_home_keeps_a_collapsed_section(client: TestClient) -> None:
    issue = _seed_assigned(client)
    client.cookies.set("keel_inbox", "assigned")
    response = client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get("/")
    assert " open" not in _panel(page.text, "assigned")
    assert "In Progress" in page.text


def test_removing_a_home_panel_hides_it_until_it_is_added(
    client: TestClient,
) -> None:
    _seed_assigned(client)
    removed = client.post(
        "/web/home/hide",
        data={"panel": "assigned", "next": "/"},
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert removed.headers["location"] == "/"
    page = client.get("/")
    assert "<h2>Assigned to me</h2>" not in page.text
    assert "Every home panel is hidden." in page.text
    assert "Add a panel" in page.text
    assert ">Assigned to me</option>" in page.text
    added = client.post(
        "/web/home/show",
        data={"panel": "assigned", "next": "/"},
        follow_redirects=False,
    )
    assert added.status_code == 303
    restored = client.get("/")
    assert "<h2>Assigned to me</h2>" in restored.text
    assert "Add a panel" not in restored.text


def test_moving_a_home_panel_up_changes_the_stack(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    tester = _tester(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Late",
            "assignee_id": tester["id"],
            "due_at": "2020-01-01T09:00:00",
        },
    )
    page = client.get("/")
    headings = re.findall(r"<h2>([^<]+)</h2>", page.text)
    assert headings[:2] == ["Due or overdue", "Assigned to me"]
    moved = client.post(
        "/web/home/move",
        data={
            "item": "assigned",
            "direction": "up",
            "visible": "due,assigned",
            "next": "/",
        },
        follow_redirects=False,
    )
    assert moved.status_code == 303
    again = client.get("/")
    assert re.findall(r"<h2>([^<]+)</h2>", again.text)[:2] == [
        "Assigned to me",
        "Due or overdue",
    ]
