from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def project_id(client: TestClient) -> int:
    response = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    return int(response.json()["id"])


def create_issue(
    client: TestClient,
    project_id: int,
    **body: object,
) -> dict[str, Any]:
    payload = {"type": "story", "title": "Something", **body}
    response = client.post(f"/api/v1/projects/{project_id}/issues", json=payload)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_a_created_issue_carries_its_key(client: TestClient, project_id: int) -> None:
    issue = create_issue(client, project_id)

    assert issue["key"] == "KEEL-1"
    assert issue["number"] == 1
    assert issue["status"] == "todo"


def test_the_reporter_defaults_to_the_acting_user(
    client: TestClient,
    project_id: int,
) -> None:
    users = client.get("/api/v1/users").json()
    issue = create_issue(client, project_id)

    assert issue["reporter_id"] == users[0]["id"]


def test_the_reporter_follows_the_user_header(
    client: TestClient,
    project_id: int,
) -> None:
    ada = client.post("/api/v1/users", json={"display_name": "Ada"}).json()

    response = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Something"},
        headers={"X-Keel-User": "Ada"},
    )
    assert response.json()["reporter_id"] == ada["id"]


def test_an_illegal_parent_type_is_refused(
    client: TestClient,
    project_id: int,
) -> None:
    epic = create_issue(client, project_id, type="epic", title="Epic")

    response = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "subtask", "title": "Subtask", "parent_id": epic["id"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "issue.invalid_parent_type"


def test_a_parent_in_another_project_is_refused(client: TestClient) -> None:
    keel = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"}).json()
    site = client.post("/api/v1/projects", json={"key": "SITE", "name": "Site"}).json()
    epic = create_issue(client, site["id"], type="epic", title="Epic")

    response = client.post(
        f"/api/v1/projects/{keel['id']}/issues",
        json={"type": "story", "title": "Story", "parent_id": epic["id"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "issue.invalid_parent"


def test_a_full_hierarchy_can_be_built(client: TestClient, project_id: int) -> None:
    epic = create_issue(client, project_id, type="epic", title="Epic")
    story = create_issue(
        client,
        project_id,
        type="story",
        title="Story",
        parent_id=epic["id"],
    )
    subtask = create_issue(
        client,
        project_id,
        type="subtask",
        title="Subtask",
        parent_id=story["id"],
    )

    children = client.get(f"/api/v1/issues/{story['id']}/children").json()
    assert [child["id"] for child in children] == [subtask["id"]]
    assert [issue["key"] for issue in (epic, story, subtask)] == [
        "KEEL-1",
        "KEEL-2",
        "KEEL-3",
    ]


def test_a_patch_changes_only_what_it_names(
    client: TestClient,
    project_id: int,
) -> None:
    epic = create_issue(client, project_id, type="epic", title="Epic")
    story = create_issue(
        client,
        project_id,
        type="story",
        title="Story",
        parent_id=epic["id"],
    )

    updated = client.patch(
        f"/api/v1/issues/{story['id']}",
        json={"status": "in_progress"},
    ).json()

    assert updated["status"] == "in_progress"
    assert updated["parent_id"] == epic["id"]
    assert updated["title"] == "Story"


def test_an_explicit_null_clears_the_parent(
    client: TestClient,
    project_id: int,
) -> None:
    epic = create_issue(client, project_id, type="epic", title="Epic")
    story = create_issue(
        client,
        project_id,
        type="story",
        title="Story",
        parent_id=epic["id"],
    )

    updated = client.patch(
        f"/api/v1/issues/{story['id']}",
        json={"parent_id": None},
    ).json()
    assert updated["parent_id"] is None


def test_the_list_endpoint_filters(client: TestClient, project_id: int) -> None:
    epic = create_issue(client, project_id, type="epic", title="Epic")
    story = create_issue(
        client,
        project_id,
        type="story",
        title="Story",
        parent_id=epic["id"],
    )

    by_type = client.get(
        f"/api/v1/projects/{project_id}/issues",
        params={"type": "story"},
    ).json()
    by_parent = client.get(
        f"/api/v1/projects/{project_id}/issues",
        params={"parent_id": epic["id"]},
    ).json()
    by_status = client.get(
        f"/api/v1/projects/{project_id}/issues",
        params={"status": "done"},
    ).json()

    assert [issue["id"] for issue in by_type] == [story["id"]]
    assert [issue["id"] for issue in by_parent] == [story["id"]]
    assert by_status == []


def test_deleting_a_parent_is_refused(client: TestClient, project_id: int) -> None:
    epic = create_issue(client, project_id, type="epic", title="Epic")
    create_issue(client, project_id, type="story", title="Story", parent_id=epic["id"])

    response = client.delete(f"/api/v1/issues/{epic['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "issue.has_children"


def test_deleting_a_leaf_succeeds(client: TestClient, project_id: int) -> None:
    issue = create_issue(client, project_id)

    assert client.delete(f"/api/v1/issues/{issue['id']}").status_code == 204
    assert client.get(f"/api/v1/issues/{issue['id']}").status_code == 404


def test_a_referenced_user_cannot_be_deleted(
    client: TestClient,
    project_id: int,
) -> None:
    ada = client.post("/api/v1/users", json={"display_name": "Ada"}).json()
    create_issue(client, project_id, assignee_id=ada["id"])

    response = client.delete(f"/api/v1/users/{ada['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "user.in_use"
