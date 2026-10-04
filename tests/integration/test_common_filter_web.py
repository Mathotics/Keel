from typing import Any

from fastapi.testclient import TestClient

Json = dict[str, Any]


def _project(client: TestClient, key: str = "KEEL") -> Json:
    created: Json = client.post(
        "/api/v1/projects",
        json={"key": key, "name": key.title()},
    ).json()
    return created


def test_clearing_every_type_shows_no_cards_and_keeps_every_column(
    client: TestClient,
) -> None:
    project = _project(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Still here"},
    )

    page = client.get("/projects/KEEL/board", params={"filters": "1"})

    assert page.status_code == 200
    assert "Still here" not in page.text
    for status in ("todo", "in_progress", "in_review", "blocked", "done", "cancelled"):
        assert f'data-status="{status}"' in page.text
    assert 'value="epic" checked' not in page.text
    assert 'value="story" checked' not in page.text
    assert 'value="subtask" checked' not in page.text


def test_a_status_filter_leaves_the_other_columns_empty(client: TestClient) -> None:
    project = _project(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Open work"},
    )

    page = client.get("/projects/KEEL/board", params={"status": "done"})
    column = page.text.split('data-status="todo"', 1)[1].split("</section>", 1)[0]

    assert "To Do" in page.text
    assert "Open work" not in column
    assert 'data-status="done"' in page.text


def test_labels_match_any_and_combine_with_assignee(client: TestClient) -> None:
    project = _project(client)
    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada", "password": "tester-password"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Ada urgent",
            "labels": ["urgent"],
            "assignee_id": ada["id"],
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Just plumbing", "labels": ["plumbing"]},
    )

    either = client.get(
        "/projects/KEEL/board",
        params=[("label", "urgent"), ("label", "plumbing")],
    )
    both = client.get(
        "/projects/KEEL/board",
        params=[("label", "urgent"), ("assignee", "Ada")],
    )

    assert "Ada urgent" in either.text
    assert "Just plumbing" in either.text
    assert "Ada urgent" in both.text
    assert "Just plumbing" not in both.text


def test_created_by_matches_the_reporter(client: TestClient) -> None:
    project = _project(client)
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Filed by tester"},
    )
    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada", "password": "tester-password"},
    ).json()

    filed = client.get("/projects/KEEL/board", params={"reporter": "Tester"})
    other = client.get("/projects/KEEL/board", params={"reporter": ada["display_name"]})
    page = client.get("/projects/KEEL/board")

    assert "Filed by tester" in filed.text
    assert "Filed by tester" not in other.text
    assert 'data-keel-lookup-empty="none"' in page.text


def test_the_calendar_uses_the_same_bar(client: TestClient) -> None:
    project = _project(client)
    users = client.get("/api/v1/users").json()
    tester = next(user for user in users if user["display_name"] == "Tester")
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "story",
            "title": "Dated story",
            "assignee_id": tester["id"],
            "due_at": "2026-10-15T09:00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={
            "type": "epic",
            "title": "Dated epic",
            "assignee_id": tester["id"],
            "due_at": "2026-10-15T09:00:00",
        },
    )

    master = client.get("/calendar", params={"month": "2026-10"})
    narrowed = client.get(
        "/calendar",
        params={"month": "2026-10", "type": "epic"},
    )
    project_page = client.get("/projects/KEEL/calendar", params={"month": "2026-10"})

    assert "Dated story" in master.text
    assert "Dated epic" in master.text
    assert 'data-keel-lookup="projects"' in master.text
    assert "Dated epic" in narrowed.text
    assert "Dated story" not in narrowed.text
    assert "month=2026-09&amp;filters=1&amp;type=epic" in narrowed.text
    assert 'keel-filters__reset" href="/calendar?month=2026-10"' in narrowed.text
    assert 'data-keel-lookup="projects"' not in project_page.text
    assert "Dated story" in project_page.text
