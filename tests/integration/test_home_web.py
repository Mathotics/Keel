from typing import Any

from fastapi.testclient import TestClient

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
    ada = client.post("/api/v1/users", json={"display_name": "Ada"}).json()
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

    client.post("/web/user", data={"user": str(ada["id"]), "next": "/"})
    as_ada = client.get("/")
    assert "For Ada" in as_ada.text
    assert "For Tester" not in as_ada.text
