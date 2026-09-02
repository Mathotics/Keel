from typing import Any
from urllib.parse import parse_qs, urlparse

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


def issue(client: TestClient, project: Json, title: str, **body: object) -> Json:
    payload = {"type": "story", "title": title, **body}
    created: Json = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json=payload,
    ).json()
    return created


def test_the_issue_page_lists_grouped_dependencies(
    client: TestClient,
    project: Json,
) -> None:
    site = client.post("/api/v1/projects", json={"key": "SITE", "name": "Site"}).json()
    local = issue(client, project, "Local")
    foreign = issue(client, site, "Foreign")
    client.post(
        "/api/v1/dependencies",
        json={
            "source_id": local["id"],
            "target_id": foreign["id"],
            "kind": "blocks",
        },
    )

    page = client.get("/issues/KEEL-1")
    assert page.status_code == 200
    assert "Dependencies" in page.text
    assert "SITE-1" in page.text
    assert "(SITE)" in page.text
    assert "Foreign" in page.text
    assert ">Add<" in page.text
    assert 'name="relation"' in page.text
    assert (
        "data-keel-autosubmit"
        not in page.text.split("Dependencies", 1)[1].split(
            "Delete issue",
            1,
        )[0]
    )


def test_a_blocks_link_can_be_added_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    source = issue(client, project, "First")
    target = issue(client, project, "Second")

    response = client.post(
        f"/web/issues/{source['id']}/dependencies",
        data={"other_id": str(target["id"]), "relation": "blocks"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    blocks, rest = page.text.split("Blocked by", 1)
    assert "KEEL-2" in blocks
    assert "Second" in blocks
    assert "KEEL-2" not in rest.split("Relates to", 1)[0]


def test_blocked_by_reverses_source_and_target(
    client: TestClient,
    project: Json,
) -> None:
    waiting = issue(client, project, "Waiting")
    blocker = issue(client, project, "Blocker")

    client.post(
        f"/web/issues/{waiting['id']}/dependencies",
        data={"other_id": str(blocker["id"]), "relation": "blocked_by"},
        follow_redirects=False,
    )
    grouped = client.get(f"/api/v1/issues/{waiting['id']}/dependencies").json()
    assert [item["key"] for item in grouped["blocked_by"]] == ["KEEL-2"]


def test_an_empty_choice_returns_to_the_issue_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    waiting = issue(client, project, "Waiting")
    issue(client, project, "Other")

    response = client.post(
        f"/web/issues/{waiting['id']}/dependencies",
        data={"other_id": "", "relation": "blocks"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        "Choose an issue"
        in parse_qs(urlparse(response.headers["location"]).query)["error"][0]
    )


def test_an_unknown_relation_returns_to_the_issue_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    waiting = issue(client, project, "Waiting")
    other = issue(client, project, "Other")

    response = client.post(
        f"/web/issues/{waiting['id']}/dependencies",
        data={"other_id": str(other["id"]), "relation": "duplicates"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        "not a valid dependency kind"
        in parse_qs(
            urlparse(response.headers["location"]).query,
        )["error"][0]
    )


def test_a_cycle_returns_to_the_issue_with_the_message(
    client: TestClient,
    project: Json,
) -> None:
    first = issue(client, project, "First")
    second = issue(client, project, "Second")
    client.post(
        "/api/v1/dependencies",
        json={
            "source_id": first["id"],
            "target_id": second["id"],
            "kind": "blocks",
        },
    )

    response = client.post(
        f"/web/issues/{second['id']}/dependencies",
        data={"other_id": str(first["id"]), "relation": "blocks"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/issues/KEEL-2?error=")
    message = parse_qs(urlparse(location).query)["error"][0]
    assert "already blocks" in message
    page = client.get(location)
    assert "already blocks" in page.text


def test_a_link_can_be_removed_from_the_issue_page(
    client: TestClient,
    project: Json,
) -> None:
    source = issue(client, project, "First")
    target = issue(client, project, "Second")
    link = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "kind": "relates_to",
        },
    ).json()

    response = client.post(
        f"/web/dependencies/{link['id']}/delete",
        data={"next": "/issues/KEEL-1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/issues/KEEL-1"
    page = client.get("/issues/KEEL-1")
    relates = page.text.split("Relates to", 1)[1]
    assert "KEEL-2" not in relates.split("This issue", 1)[0]


def test_the_board_shows_a_blocker_marker(
    client: TestClient,
    project: Json,
) -> None:
    blocker = issue(client, project, "Blocker")
    waiting = issue(client, project, "Waiting")
    client.post(
        "/api/v1/dependencies",
        json={
            "source_id": blocker["id"],
            "target_id": waiting["id"],
            "kind": "blocks",
        },
    )

    board = client.get("/projects/KEEL/board")
    assert "1 blocker" in board.text
    assert "keel-blockers" in board.text
    backlog = client.get("/projects/KEEL/backlog")
    assert "keel-blockers" in backlog.text
    css = client.get("/assets/brand.css").text
    assert ".keel-blockers" in css
