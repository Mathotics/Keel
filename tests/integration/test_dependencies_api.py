from typing import Any

import pytest
from fastapi.testclient import TestClient

Json = dict[str, Any]


@pytest.fixture
def project_id(client: TestClient) -> int:
    return int(
        client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"}).json()[
            "id"
        ],
    )


def create_issue(
    client: TestClient,
    project_id: int,
    **body: object,
) -> Json:
    payload = {"type": "story", "title": "Something", **body}
    created: Json = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json=payload,
    ).json()
    return created


def test_a_blocks_link_is_created_and_grouped(
    client: TestClient,
    project_id: int,
) -> None:
    source = create_issue(client, project_id, title="First")
    target = create_issue(client, project_id, title="Second")

    created = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "kind": "blocks",
        },
    )
    assert created.status_code == 201
    assert created.json()["kind"] == "blocks"

    grouped = client.get(f"/api/v1/issues/{source['id']}/dependencies").json()
    assert [item["key"] for item in grouped["blocks"]] == ["KEEL-2"]
    assert grouped["blocked_by"] == []
    waiting = client.get(f"/api/v1/issues/{target['id']}/dependencies").json()
    assert [item["key"] for item in waiting["blocked_by"]] == ["KEEL-1"]


def test_a_cycle_is_refused_with_the_coded_error(
    client: TestClient,
    project_id: int,
) -> None:
    first = create_issue(client, project_id, title="First")
    second = create_issue(client, project_id, title="Second")
    client.post(
        "/api/v1/dependencies",
        json={
            "source_id": first["id"],
            "target_id": second["id"],
            "kind": "blocks",
        },
    )

    response = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": second["id"],
            "target_id": first["id"],
            "kind": "blocks",
        },
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "dependency.cycle"
    assert detail["context"]["source_id"] == second["id"]
    assert detail["context"]["target_id"] == first["id"]


def test_a_self_link_is_refused(client: TestClient, project_id: int) -> None:
    issue = create_issue(client, project_id, title="Alone")
    response = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": issue["id"],
            "target_id": issue["id"],
            "kind": "relates_to",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "dependency.self_link"


def test_a_duplicate_link_is_refused(client: TestClient, project_id: int) -> None:
    source = create_issue(client, project_id, title="First")
    target = create_issue(client, project_id, title="Second")
    payload = {
        "source_id": source["id"],
        "target_id": target["id"],
        "kind": "blocks",
    }
    assert client.post("/api/v1/dependencies", json=payload).status_code == 201
    response = client.post("/api/v1/dependencies", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "dependency.duplicate"


def test_links_may_cross_projects(client: TestClient, project_id: int) -> None:
    site = client.post("/api/v1/projects", json={"key": "SITE", "name": "Site"}).json()
    local = create_issue(client, project_id, title="Local")
    foreign = create_issue(client, site["id"], title="Foreign")

    created = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": local["id"],
            "target_id": foreign["id"],
            "kind": "blocks",
        },
    )
    assert created.status_code == 201
    grouped = client.get(f"/api/v1/issues/{local['id']}/dependencies").json()
    assert grouped["blocks"][0]["key"] == "SITE-1"
    assert grouped["blocks"][0]["project_key"] == "SITE"


def test_a_link_can_be_removed(client: TestClient, project_id: int) -> None:
    source = create_issue(client, project_id, title="First")
    target = create_issue(client, project_id, title="Second")
    link = client.post(
        "/api/v1/dependencies",
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "kind": "relates_to",
        },
    ).json()

    deleted = client.delete(f"/api/v1/dependencies/{link['id']}")
    assert deleted.status_code == 204
    grouped = client.get(f"/api/v1/issues/{source['id']}/dependencies").json()
    assert grouped["relates_to"] == []


def test_an_unknown_dependency_is_not_found(client: TestClient) -> None:
    assert client.delete("/api/v1/dependencies/404").status_code == 404


def test_the_board_and_issue_report_unresolved_blockers(
    client: TestClient,
    project_id: int,
) -> None:
    blocker = create_issue(client, project_id, title="Blocker")
    waiting = create_issue(client, project_id, title="Waiting")
    client.post(
        "/api/v1/dependencies",
        json={
            "source_id": blocker["id"],
            "target_id": waiting["id"],
            "kind": "blocks",
        },
    )

    board = client.get(f"/api/v1/projects/{project_id}/board").json()
    by_title = {
        issue["title"]: issue["unresolved_blockers"]
        for column in board["columns"]
        for issue in column["issues"]
    }
    assert by_title["Waiting"] == 1
    assert by_title["Blocker"] == 0
    assert (
        client.get(f"/api/v1/issues/{waiting['id']}").json()["unresolved_blockers"] == 1
    )

    client.patch(f"/api/v1/issues/{blocker['id']}", json={"status": "done"})
    backlog = client.get(f"/api/v1/projects/{project_id}/backlog").json()
    waiting_row = next(item for item in backlog if item["title"] == "Waiting")
    assert waiting_row["unresolved_blockers"] == 0
