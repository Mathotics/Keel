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


def test_an_issue_is_edited_on_its_page(client: TestClient, project: Json) -> None:
    submit_issue(client, project, title="Original")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    page = client.get("/issues/KEEL-1")
    assert "Original" in page.text
    assert ">Edit<" not in page.text
    assert 'name="title"' in page.text
    assert 'name="type"' in page.text
    assert 'name="description"' in page.text
    assert 'name="parent_id"' in page.text

    renamed = client.post(
        f"/web/issues/{issue_id}/title",
        data={"title": "Renamed"},
        follow_redirects=False,
    )
    assert renamed.headers["location"] == "/issues/KEEL-1"
    assert "Renamed" in client.get("/issues/KEEL-1").text

    moved = client.post(
        f"/web/issues/{issue_id}/status",
        data={"status": "in_progress", "next": "/issues/KEEL-1"},
        follow_redirects=False,
    )
    assert moved.headers["location"] == "/issues/KEEL-1"
    due = client.post(
        f"/web/issues/{issue_id}/due",
        data={"due_at": "2026-11-02T08:15"},
        follow_redirects=False,
    )
    assert due.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert "In Progress" in page.text
    assert 'value="2026-11-02T08:15"' in page.text


def test_the_old_edit_url_redirects_to_the_issue(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    response = client.get("/issues/KEEL-1/edit", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/issues/KEEL-1"


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


def test_the_issue_page_shows_its_metadata(client: TestClient, project: Json) -> None:
    submit_issue(client, project, title="Ready", due_at="2026-09-15T17:00")

    page = client.get("/issues/KEEL-1")
    assert "Created on" in page.text
    assert "Updated on" in page.text
    assert "Due date" in page.text
    assert 'name="due_at"' in page.text
    assert 'type="datetime-local"' in page.text
    assert 'value="2026-09-15T17:00"' in page.text
    assert "Reporter" in page.text
    assert 'name="status"' in page.text
    assert 'value="todo" selected' in page.text or 'value="todo"selected' in page.text
    assert 'name="assignee_id"' in page.text
    assert 'name="sprint_id"' in page.text
    assert 'name="estimate"' in page.text
    assert 'name="remaining"' in page.text
    assert "data-keel-autosubmit" in page.text
    assert "keel-autosubmit__fallback" in page.text


def test_assignee_can_be_changed_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]
    person = client.get("/api/v1/users").json()[0]["id"]

    response = client.post(
        f"/web/issues/{issue_id}/assignee",
        data={"assignee_id": str(person)},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert f'value="{person}" selected' in page.text or (
        f'value="{person}"selected' in page.text
    )
    assert client.get(f"/api/v1/issues/{issue_id}").json()["assignee_id"] == person

    cleared = client.post(
        f"/web/issues/{issue_id}/assignee",
        data={"assignee_id": ""},
        follow_redirects=False,
    )
    assert cleared.headers["location"] == "/issues/KEEL-1"
    assert client.get(f"/api/v1/issues/{issue_id}").json()["assignee_id"] is None


def test_status_can_be_changed_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    response = client.post(
        f"/web/issues/{issue_id}/status",
        data={"status": "in_review", "next": "/issues/KEEL-1"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert 'value="in_review" selected' in page.text or (
        'value="in_review"selected' in page.text
    )
    assert client.get(f"/api/v1/issues/{issue_id}").json()["status"] == "in_review"


def test_due_date_can_be_changed_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    response = client.post(
        f"/web/issues/{issue_id}/due",
        data={"due_at": "2026-10-01T09:30"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert 'value="2026-10-01T09:30"' in page.text
    stored = client.get(f"/api/v1/issues/{issue_id}").json()
    assert stored["due_at"].startswith("2026-10-01T09:30")

    cleared = client.post(
        f"/web/issues/{issue_id}/due",
        data={"due_at": ""},
        follow_redirects=False,
    )
    assert cleared.headers["location"] == "/issues/KEEL-1"
    assert client.get(f"/api/v1/issues/{issue_id}").json()["due_at"] is None


def test_an_unreadable_due_date_returns_to_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    response = client.post(
        f"/web/issues/{issue_id}/due",
        data={"due_at": "next tuesday"},
        follow_redirects=False,
    )

    assert response.headers["location"].startswith("/issues/KEEL-1?error=")


def test_created_on_is_not_editable(client: TestClient, project: Json) -> None:
    submit_issue(client, project, title="Ready")

    page = client.get("/issues/KEEL-1")
    assert 'name="due_at"' in page.text
    assert "Created on" in page.text
    assert 'name="created_at"' not in page.text
    assert 'name="updated_at"' not in page.text


def test_type_and_description_can_be_changed_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]

    typed = client.post(
        f"/web/issues/{issue_id}/type",
        data={"type": "epic"},
        follow_redirects=False,
    )
    assert typed.headers["location"] == "/issues/KEEL-1"
    described = client.post(
        f"/web/issues/{issue_id}/description",
        data={"description": "A longer note."},
        follow_redirects=False,
    )
    assert described.headers["location"] == "/issues/KEEL-1"
    stored = client.get(f"/api/v1/issues/{issue_id}").json()
    assert stored["type"] == "epic"
    assert stored["description"] == "A longer note."


def test_parent_can_be_changed_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, type="epic", title="Epic")
    epic_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]
    submit_issue(client, project, title="Story")
    story_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[1]["id"]

    response = client.post(
        f"/web/issues/{story_id}/parent",
        data={"parent_id": str(epic_id)},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/issues/KEEL-2"
    assert client.get(f"/api/v1/issues/{story_id}").json()["parent_id"] == epic_id

    illegal = client.post(
        f"/web/issues/{story_id}/type",
        data={"type": "epic"},
        follow_redirects=False,
    )
    assert illegal.headers["location"].startswith("/issues/KEEL-2?error=")


def test_the_project_list_shows_due_and_created(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, title="Ready")
    page = client.get("/projects/KEEL")
    assert "Due date" in page.text
    assert "Created on" in page.text


def test_effort_round_trips_through_shorthand(
    client: TestClient,
    project: Json,
) -> None:
    location = submit_issue(client, project, title="Sized", estimate="1h 30m")
    issue_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]
    page = client.get(location)
    assert 'value="1h 30m"' in page.text
    assert client.get(f"/api/v1/issues/{issue_id}").json()["estimate_minutes"] == 90

    saved = client.post(
        f"/web/issues/{issue_id}/remaining",
        data={"remaining": "45m"},
        follow_redirects=False,
    )
    assert saved.headers["location"] == "/issues/KEEL-1"
    assert client.get(f"/api/v1/issues/{issue_id}").json()["remaining_minutes"] == 45
    assert 'value="45m"' in client.get("/issues/KEEL-1").text

    refused = client.post(
        f"/web/issues/{issue_id}/estimate",
        data={"estimate": "1h30"},
        follow_redirects=False,
    )
    assert refused.headers["location"].startswith("/issues/KEEL-1?error=")


def test_an_epic_page_shows_subtree_progress(
    client: TestClient,
    project: Json,
) -> None:
    submit_issue(client, project, type="epic", title="Epic", estimate="2h")
    epic_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[0]["id"]
    submit_issue(
        client,
        project,
        type="story",
        title="Story",
        parent_id=str(epic_id),
        estimate="1h",
    )
    story_id = client.get(f"/api/v1/projects/{project['id']}/issues").json()[1]["id"]
    client.patch(f"/api/v1/issues/{story_id}", json={"status": "done"})

    page = client.get("/issues/KEEL-1")
    assert "Including descendants: 3h estimate, 3h remaining. 1 of 1 done." in page.text
    assert 'value="2h"' in page.text
