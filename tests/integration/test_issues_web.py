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


def submit_issue(client: TestClient, project: Json, **fields: str) -> str:
    data = {"type": "story", "title": "Something", "status": "todo", **fields}
    response = client.post(
        f"/web/projects/{project['id']}/issues",
        data=data,
        follow_redirects=False,
    )
    return response.headers["location"]


def test_the_new_issue_form_renders(client: TestClient, project: Json) -> None:
    page = client.get("/projects/KEEL/issues/new")

    assert page.status_code == 200
    assert 'name="title"' in page.text
    assert "Epic" in page.text


def test_an_issue_is_created_and_lands_on_its_page(
    client: TestClient,
    project: Json,
) -> None:
    location = submit_issue(client, project, title="Rework onboarding")

    assert location == "/issues/KEEL-1"
    page = client.get(location)
    assert page.status_code == 200
    assert "Rework onboarding" in page.text


def test_the_issue_page_shows_its_children(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, type="epic", title="Epic")
    epic_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]
    submit_issue(client, project, title="Story", parent_id=str(epic_id))

    page = client.get("/issues/KEEL-1")
    assert "KEEL-2" in page.text
    assert "Story" in page.text


def test_an_illegal_parent_returns_to_the_form_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, type="epic", title="Epic")
    epic_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    location = submit_issue(
        client,
        project,
        type="subtask",
        title="Subtask",
        parent_id=str(epic_id),
    )

    assert location.startswith("/projects/KEEL/issues/new?error=")
    page = client.get(location)
    assert "never has a parent" in page.text or "may only sit under" in page.text


def test_an_issue_is_edited_from_its_form(client: TestClient, project: Json) -> None:
    submit_issue(client, project, title="Original")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    form = client.get("/issues/KEEL-1/edit")
    assert "Original" in form.text

    response = client.post(
        f"/web/issues/{issue_id}/update",
        data={"type": "story", "title": "Renamed", "status": "in_progress"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert "Renamed" in page.text
    assert "In Progress" in page.text


def test_deleting_a_parent_returns_the_coded_message(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, type="epic", title="Epic")
    epic_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]
    submit_issue(client, project, title="Story", parent_id=str(epic_id))

    response = client.post(
        f"/web/issues/{epic_id}/delete",
        follow_redirects=False,
    )

    assert response.headers["location"].startswith("/issues/KEEL-1?error=")


def test_deleting_a_leaf_returns_to_the_project(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Story")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    response = client.post(
        f"/web/issues/{issue_id}/delete",
        follow_redirects=False,
    )

    assert response.headers["location"] == "/projects/KEEL"


def test_an_unknown_issue_page_is_not_found(client: TestClient) -> None:
    assert client.get("/issues/KEEL-99").status_code == 404
