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


def test_the_board_has_a_column_for_every_status(
    client: TestClient,
    project_id: int,
) -> None:
    board = client.get(f"/api/v1/projects/{project_id}/board").json()

    assert [column["status"] for column in board["columns"]] == [
        "todo",
        "in_progress",
        "in_review",
        "blocked",
        "done",
    ]
    assert [column["label"] for column in board["columns"]][0] == "To Do"
    assert board["project_id"] == project_id


def test_issues_appear_in_their_status_column(
    client: TestClient,
    project_id: int,
) -> None:
    issue = create_issue(client, project_id, title="Ready")
    client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "in_review"})

    board = client.get(f"/api/v1/projects/{project_id}/board").json()
    by_status = {column["status"]: column["issues"] for column in board["columns"]}

    assert [card["key"] for card in by_status["in_review"]] == ["KEEL-1"]
    assert by_status["todo"] == []


def test_a_repeated_type_parameter_filters_the_board(
    client: TestClient,
    project_id: int,
) -> None:
    create_issue(client, project_id, type="epic", title="Epic")
    create_issue(client, project_id, type="story", title="Story")
    create_issue(client, project_id, type="subtask", title="Subtask")

    board = client.get(
        f"/api/v1/projects/{project_id}/board",
        params=[("type", "epic"), ("type", "subtask")],
    ).json()
    titles = [
        issue["title"] for column in board["columns"] for issue in column["issues"]
    ]

    assert titles == ["Epic", "Subtask"]


def test_an_assignee_parameter_filters_the_board(
    client: TestClient,
    project_id: int,
) -> None:
    ada = client.post("/api/v1/users", json={"display_name": "Ada"}).json()
    create_issue(client, project_id, title="Ada's", assignee_id=ada["id"])
    create_issue(client, project_id, title="Open")

    assigned = client.get(
        f"/api/v1/projects/{project_id}/board",
        params={"assignee": ada["id"]},
    ).json()
    open_only = client.get(
        f"/api/v1/projects/{project_id}/board",
        params={"assignee": "unassigned"},
    ).json()

    def titles(board: Json) -> list[str]:
        return [
            issue["title"] for column in board["columns"] for issue in column["issues"]
        ]

    assert titles(assigned) == ["Ada's"]
    assert titles(open_only) == ["Open"]


def test_a_sprint_parameter_filters_the_board(
    client: TestClient,
    project_id: int,
) -> None:
    sprint = client.post(
        f"/api/v1/projects/{project_id}/sprints",
        json={"name": "Sprint 1"},
    ).json()
    create_issue(client, project_id, title="In sprint", sprint_id=sprint["id"])
    create_issue(client, project_id, title="Waiting")

    scheduled = client.get(
        f"/api/v1/projects/{project_id}/board",
        params={"sprint": sprint["id"]},
    ).json()
    waiting = client.get(
        f"/api/v1/projects/{project_id}/board",
        params={"sprint": "unscheduled"},
    ).json()

    def titles(board: Json) -> list[str]:
        return [
            issue["title"] for column in board["columns"] for issue in column["issues"]
        ]

    assert titles(scheduled) == ["In sprint"]
    assert titles(waiting) == ["Waiting"]


def test_an_unknown_project_board_is_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/projects/404/board").status_code == 404
