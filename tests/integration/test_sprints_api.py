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


def create_sprint(client: TestClient, project_id: int, **body: object) -> Json:
    payload = {"name": "Sprint 1", **body}
    response = client.post(f"/api/v1/projects/{project_id}/sprints", json=payload)
    assert response.status_code == 201, response.text
    created: Json = response.json()
    return created


def test_a_created_sprint_is_planned(client: TestClient, project_id: int) -> None:
    sprint = create_sprint(client, project_id, goal="Ship it")

    assert sprint["state"] == "planned"
    assert sprint["goal"] == "Ship it"
    assert sprint["project_id"] == project_id


def test_the_list_can_filter_by_state(client: TestClient, project_id: int) -> None:
    create_sprint(client, project_id, name="Waiting")
    active = create_sprint(client, project_id, name="Now")
    client.post(f"/api/v1/sprints/{active['id']}/start")

    planned = client.get(
        f"/api/v1/projects/{project_id}/sprints",
        params={"state": "planned"},
    ).json()
    assert [item["name"] for item in planned] == ["Waiting"]


def test_starting_a_second_sprint_is_refused(
    client: TestClient,
    project_id: int,
) -> None:
    first = create_sprint(client, project_id, name="One")
    second = create_sprint(client, project_id, name="Two")
    assert client.post(f"/api/v1/sprints/{first['id']}/start").status_code == 200

    response = client.post(f"/api/v1/sprints/{second['id']}/start")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "sprint.already_active"


def test_completion_reports_what_was_carried(
    client: TestClient,
    project_id: int,
) -> None:
    current = create_sprint(client, project_id, name="Now")
    nxt = create_sprint(
        client,
        project_id,
        name="Next",
        starts_on="2026-10-01",
    )
    issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Carry me", "sprint_id": current["id"]},
    ).json()
    client.post(f"/api/v1/sprints/{current['id']}/start")

    result = client.post(f"/api/v1/sprints/{current['id']}/complete").json()

    assert result["sprint"]["state"] == "completed"
    assert result["carried_over"] == 1
    assert result["carried_to_sprint_id"] == nxt["id"]
    moved = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert moved["sprint_id"] == nxt["id"]


def test_an_issue_cannot_join_another_projects_sprint(client: TestClient) -> None:
    keel = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"}).json()
    site = client.post("/api/v1/projects", json={"key": "SITE", "name": "Site"}).json()
    foreign = create_sprint(client, site["id"], name="Site sprint")
    issue = client.post(
        f"/api/v1/projects/{keel['id']}/issues",
        json={"type": "story", "title": "Local"},
    ).json()

    response = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"sprint_id": foreign["id"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "sprint.project_mismatch"


def test_deleting_a_sprint_unschedules_its_issues(
    client: TestClient,
    project_id: int,
) -> None:
    sprint = create_sprint(client, project_id)
    issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Work", "sprint_id": sprint["id"]},
    ).json()

    assert client.delete(f"/api/v1/sprints/{sprint['id']}").status_code == 204
    assert client.get(f"/api/v1/issues/{issue['id']}").json()["sprint_id"] is None


def test_the_backlog_omits_scheduled_and_done_issues(
    client: TestClient,
    project_id: int,
) -> None:
    sprint = create_sprint(client, project_id)
    waiting = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Waiting"},
    ).json()
    client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Scheduled", "sprint_id": sprint["id"]},
    )
    done = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Finished"},
    ).json()
    client.patch(f"/api/v1/issues/{done['id']}", json={"status": "done"})

    backlog = client.get(f"/api/v1/projects/{project_id}/backlog").json()
    assert [item["id"] for item in backlog] == [waiting["id"]]


def test_issue_list_filters_by_sprint(client: TestClient, project_id: int) -> None:
    sprint = create_sprint(client, project_id)
    scheduled = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "In", "sprint_id": sprint["id"]},
    ).json()
    client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Out"},
    )

    listed = client.get(
        f"/api/v1/projects/{project_id}/issues",
        params={"sprint_id": sprint["id"]},
    ).json()
    unscheduled = client.get(
        f"/api/v1/projects/{project_id}/issues",
        params={"unscheduled": True},
    ).json()

    assert [item["id"] for item in listed] == [scheduled["id"]]
    assert [item["title"] for item in unscheduled] == ["Out"]


def test_read_sprint_includes_its_issues(client: TestClient, project_id: int) -> None:
    sprint = create_sprint(
        client,
        project_id,
        starts_on="2026-09-01",
        ends_on="2026-09-14",
    )
    issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"type": "story", "title": "Work", "sprint_id": sprint["id"]},
    ).json()

    detail = client.get(f"/api/v1/sprints/{sprint['id']}").json()
    assert detail["starts_on"] == "2026-09-01"
    assert [item["id"] for item in detail["issues"]] == [issue["id"]]


def test_a_sprint_can_be_renamed_and_dated(
    client: TestClient,
    project_id: int,
) -> None:
    sprint = create_sprint(client, project_id)

    updated = client.patch(
        f"/api/v1/sprints/{sprint['id']}",
        json={
            "name": "Sprint 1a",
            "starts_on": "2026-09-01",
            "ends_on": "2026-09-14",
        },
    )

    assert updated.status_code == 200, updated.text
    body: Json = updated.json()
    assert body["name"] == "Sprint 1a"
    assert body["starts_on"] == "2026-09-01"
    assert body["ends_on"] == "2026-09-14"


def test_an_end_before_the_start_is_refused(
    client: TestClient,
    project_id: int,
) -> None:
    response = client.post(
        f"/api/v1/projects/{project_id}/sprints",
        json={"name": "Sprint 1", "starts_on": "2026-09-10", "ends_on": "2026-09-01"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "sprint.invalid"
