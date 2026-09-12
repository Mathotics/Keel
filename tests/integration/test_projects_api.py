from typing import Any

from fastapi.testclient import TestClient


def create_project(
    client: TestClient,
    key: str = "KEEL",
    name: str = "Keel",
) -> dict[str, Any]:
    response = client.post("/api/v1/projects", json={"key": key, "name": name})
    assert response.status_code == 201
    created: dict[str, Any] = response.json()
    return created


def test_a_project_round_trips(client: TestClient) -> None:
    created = create_project(client)

    read = client.get(f"/api/v1/projects/{created['id']}")
    assert read.status_code == 200
    assert read.json()["key"] == "KEEL"


def test_projects_are_listed(client: TestClient) -> None:
    create_project(client, "KEEL", "Keel")
    create_project(client, "SITE", "Site")

    listed = client.get("/api/v1/projects").json()
    assert [project["key"] for project in listed] == ["KEEL", "SITE"]


def test_a_duplicate_key_is_a_coded_conflict(client: TestClient) -> None:
    create_project(client)

    response = client.post("/api/v1/projects", json={"key": "KEEL", "name": "Other"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "project.duplicate_key"


def test_a_malformed_key_fails_validation(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"key": "1", "name": "Keel"})
    assert response.status_code == 422


def test_a_project_can_be_renamed_but_not_rekeyed(client: TestClient) -> None:
    created = create_project(client)

    updated = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"name": "Keel Tracker"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Keel Tracker"
    assert updated.json()["key"] == "KEEL"


def test_deleting_a_project_removes_it(client: TestClient) -> None:
    created = create_project(client)

    assert client.delete(f"/api/v1/projects/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{created['id']}").status_code == 404


def test_an_unknown_project_is_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/projects/404").status_code == 404


def test_a_new_project_has_auto_sprint_off(client: TestClient) -> None:
    created = create_project(client)
    assert created["sprint_cadence"] == "off"
    assert created["sprint_cadence_days"] is None


def test_a_project_can_enable_weekly_auto_sprint(client: TestClient) -> None:
    created = create_project(client)

    updated = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"sprint_cadence": "weekly"},
    )
    assert updated.status_code == 200
    assert updated.json()["sprint_cadence"] == "weekly"
    sprints = client.get(f"/api/v1/projects/{created['id']}/sprints").json()
    assert len(sprints) == 1
    assert sprints[0]["state"] == "active"


def test_every_n_days_without_a_count_is_refused(client: TestClient) -> None:
    created = create_project(client)
    response = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"sprint_cadence": "every_n_days"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "project.invalid_cadence"
