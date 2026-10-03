from typing import Any

from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD

Json = dict[str, Any]


def _project(client: TestClient) -> int:
    created = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    return int(created.json()["id"])


def _issue(client: TestClient, project_id: int) -> Json:
    created: Json = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Something"},
    ).json()
    return created


def test_comments_are_created_and_listed_oldest_first(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    first = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "First"},
    )
    second = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "Second"},
    )
    assert first.status_code == 201
    listed = client.get(f"/api/v1/issues/{issue['id']}/comments").json()
    assert [comment["body"] for comment in listed] == ["First", "Second"]
    assert listed[0]["id"] == first.json()["id"]
    assert listed[1]["id"] == second.json()["id"]


def test_a_comment_is_authored_by_the_acting_user(client: TestClient) -> None:
    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada", "password": TEST_PASSWORD},
    ).json()
    issue = _issue(client, _project(client))

    client.post(
        "/login",
        data={"username": "Ada", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    created = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "From Ada"},
    )
    assert created.status_code == 201
    assert created.json()["author_id"] == ada["id"]


def test_a_blank_comment_is_refused(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    response = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "  "},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "comment.invalid"


def test_a_comment_author_cannot_be_deleted(client: TestClient) -> None:
    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada", "password": TEST_PASSWORD},
    ).json()
    issue = _issue(client, _project(client))
    client.post(
        "/login",
        data={"username": "Ada", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "From Ada"},
    )
    client.post(
        "/login",
        data={"username": "Tester", "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    response = client.delete(f"/api/v1/users/{ada['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "user.in_use"


def test_a_comment_can_be_deleted(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    comment = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "Note"},
    ).json()

    assert client.delete(f"/api/v1/comments/{comment['id']}").status_code == 204
    assert client.get(f"/api/v1/issues/{issue['id']}/comments").json() == []
