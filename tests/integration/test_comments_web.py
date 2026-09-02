from typing import Any
from urllib.parse import parse_qs, urlparse

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


def test_the_issue_page_lists_comments(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "A decision"},
    )

    page = client.get("/issues/KEEL-1")
    assert page.status_code == 200
    assert "Comments" in page.text
    assert "A decision" in page.text
    assert ">Add comment<" in page.text
    assert (
        "data-keel-autosubmit"
        not in page.text.split("Comments", 1)[1].split(
            "Delete issue",
            1,
        )[0]
    )


def test_a_comment_can_be_added_from_the_issue_page(client: TestClient) -> None:
    issue = _issue(client, _project(client))

    response = client.post(
        f"/web/issues/{issue['id']}/comments",
        data={"body": "From the form"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert "From the form" in page.text
    users = client.get("/api/v1/users").json()
    assert users[0]["display_name"] in page.text


def test_a_blank_comment_returns_to_the_issue_with_the_message(
    client: TestClient,
) -> None:
    issue = _issue(client, _project(client))
    response = client.post(
        f"/web/issues/{issue['id']}/comments",
        data={"body": "  "},
        follow_redirects=False,
    )
    assert response.status_code == 303
    message = parse_qs(urlparse(response.headers["location"]).query)["error"][0]
    assert "body" in message.lower()


def test_a_comment_can_be_removed_from_the_issue_page(client: TestClient) -> None:
    issue = _issue(client, _project(client))
    comment = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "Temporary"},
    ).json()

    response = client.post(
        f"/web/comments/{comment['id']}/delete",
        data={"next": "/issues/KEEL-1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    assert "Temporary" not in page.text
    assert "No comments yet." in page.text
