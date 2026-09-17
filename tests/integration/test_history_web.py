from typing import Any

from fastapi.testclient import TestClient

Json = dict[str, Any]


def _project(client: TestClient) -> Json:
    created: Json = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    return created


def _issue(client: TestClient, project: Json) -> Json:
    created: Json = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Something"},
    ).json()
    return created


def _history(page_text: str) -> str:
    return page_text.split("History", 1)[1].split("Comments", 1)[0]


def test_a_new_issue_shows_empty_history(client: TestClient) -> None:
    _issue(client, _project(client))
    page = client.get("/issues/KEEL-1")
    assert page.status_code == 200
    assert page.text.index("History") < page.text.index("Comments")
    assert "No history yet." in _history(page.text)


def test_a_status_change_appears_above_comments(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    response = client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/issues/KEEL-1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get("/issues/KEEL-1")
    history = _history(page.text)
    assert "No history yet." not in history
    assert "Tester — status To Do → In Progress" in history
    assert "Remove" not in history
    assert ">Add comment<" not in history


def test_a_noop_status_save_does_not_add_a_line(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/issues/KEEL-1"},
        follow_redirects=False,
    )
    client.post(
        f"/web/issues/{issue['id']}/status",
        data={"status": "in_progress", "next": "/issues/KEEL-1"},
        follow_redirects=False,
    )
    page = client.get("/issues/KEEL-1")
    history = _history(page.text)
    assert history.count("status To Do → In Progress") == 1
    assert "In Progress → In Progress" not in history


def test_a_title_edit_appears_in_history(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    client.post(
        f"/web/issues/{issue['id']}/title",
        data={"title": "Renamed"},
        follow_redirects=False,
    )
    page = client.get("/issues/KEEL-1")
    history = _history(page.text)
    assert "No history yet." not in history
    assert "Tester — title Something → Renamed" in history


def test_a_description_edit_appears_in_history(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    client.post(
        f"/web/issues/{issue['id']}/description",
        data={"description": "A note"},
        follow_redirects=False,
    )
    page = client.get("/issues/KEEL-1")
    history = _history(page.text)
    assert "Tester — description none → A note" in history


def test_api_patch_uses_the_acting_user(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    patched = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"remaining_minutes": 90},
    )
    assert patched.status_code == 200
    page = client.get("/issues/KEEL-1")
    assert "Tester — remaining none → 1h 30m" in _history(page.text)


def test_label_changes_appear_in_history(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"labels": ["urgent"]},
    )
    page = client.get("/issues/KEEL-1")
    assert "Tester — labels none → urgent" in _history(page.text)
