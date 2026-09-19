from typing import Any

import pytest
from fastapi.testclient import TestClient

Json = dict[str, Any]


@pytest.fixture
def project(client: TestClient) -> Json:
    created: Json = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    return created


def test_the_project_list_page_lists_projects(
    client: TestClient,
    project: Json,
) -> None:
    page = client.get("/projects")

    assert page.status_code == 200
    assert "KEEL" in page.text
    assert "/projects/KEEL" in page.text


def test_a_project_is_created_from_the_form(client: TestClient) -> None:
    response = client.post(
        "/web/projects",
        data={"key": "site", "name": "Site"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/projects/SITE"


def test_a_bad_key_returns_to_the_form_with_the_message(client: TestClient) -> None:
    response = client.post(
        "/web/projects",
        data={"key": "1", "name": "Site"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/projects?error=")


def test_the_project_page_shows_status_counts(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Something"},
    )

    page = client.get("/projects/KEEL")
    assert page.status_code == 200
    assert "To Do" in page.text
    assert "KEEL-1" in page.text


def test_an_unknown_project_page_is_not_found(client: TestClient) -> None:
    assert client.get("/projects/NOPE").status_code == 404


def test_a_project_is_renamed_from_the_form(
    client: TestClient,
    project: Json,
) -> None:
    client.post(
        f"/web/projects/{project['id']}/update",
        data={"name": "Keel Tracker", "description": "A tracker"},
    )

    page = client.get("/projects/KEEL")
    assert "Keel Tracker" in page.text


def test_a_blank_name_on_update_returns_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    response = client.post(
        f"/web/projects/{project['id']}/update",
        data={"name": "  ", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/projects/KEEL?error=")
    assert "needs a name" in client.get(location).text


def test_a_project_is_deleted_from_the_form(
    client: TestClient,
    project: Json,
) -> None:
    response = client.post(
        f"/web/projects/{project['id']}/delete",
        follow_redirects=False,
    )

    assert response.headers["location"] == "/projects"
    assert client.get("/projects/KEEL").status_code == 404


def test_the_project_form_saves_sprint_cadence(
    client: TestClient,
    project: Json,
) -> None:
    page = client.get("/projects/KEEL")
    assert 'name="sprint_cadence"' in page.text
    assert 'name="sprint_cadence_days"' in page.text
    assert 'name="sprint_ahead"' in page.text

    saved = client.post(
        f"/web/projects/{project['id']}/update",
        data={
            "name": "Keel",
            "description": "",
            "sprint_cadence": "weekly",
            "sprint_cadence_days": "",
            "sprint_ahead": "2",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    location = saved.headers["location"]
    assert "notice=" in location
    follow = client.get(location)
    assert "Opened" in follow.text
    assert "automatically" in follow.text
    body = client.get("/api/v1/projects/" + str(project["id"])).json()
    assert body["sprint_cadence"] == "weekly"
    assert body["sprint_ahead"] == 2
    sprints = client.get(f"/api/v1/projects/{project['id']}/sprints").json()
    assert len(sprints) == 3


def test_an_unknown_cadence_returns_to_the_project_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    response = client.post(
        f"/web/projects/{project['id']}/update",
        data={
            "name": "Keel",
            "description": "",
            "sprint_cadence": "whenever",
            "sprint_cadence_days": "abc",
            "sprint_ahead": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/projects/KEEL?error=")
    assert "not a sprint cadence" in client.get(location).text


def test_a_non_numeric_day_count_returns_to_the_project_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    response = client.post(
        f"/web/projects/{project['id']}/update",
        data={
            "name": "Keel",
            "description": "",
            "sprint_cadence": "weekly",
            "sprint_cadence_days": "abc",
            "sprint_ahead": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/projects/KEEL?error=")
    assert "at least 1" in client.get(location).text


def test_a_non_numeric_ahead_count_returns_to_the_project_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    response = client.post(
        f"/web/projects/{project['id']}/update",
        data={
            "name": "Keel",
            "description": "",
            "sprint_cadence": "weekly",
            "sprint_cadence_days": "",
            "sprint_ahead": "abc",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/projects/KEEL?error=")
    assert "Sprints in advance" in client.get(location).text
