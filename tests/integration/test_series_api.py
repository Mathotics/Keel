from fastapi.testclient import TestClient


def test_the_series_api_creates_and_pauses(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/series",
        json={
            "title": "Backup",
            "type": "story",
            "spawn_mode": "calendar",
            "sprint_basis": "created_on",
            "freq": "daily",
            "starts_on": "2026-09-12",
            "look_ahead_n": 1,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["cadence_summary"] == "Daily"
    assert body["priority"] == "p4"
    paused = client.post(f"/api/v1/series/{body['id']}/pause")
    assert paused.json()["state"] == "paused"
    listed = client.get(f"/api/v1/projects/{project['id']}/series").json()
    assert listed[0]["id"] == body["id"]
    fetched = client.get(f"/api/v1/series/{body['id']}")
    assert fetched.status_code == 200
    patched = client.patch(
        f"/api/v1/series/{body['id']}",
        json={"title": "Nightly backup", "state": "active", "priority": "p2"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Nightly backup"
    assert patched.json()["state"] == "active"
    assert patched.json()["priority"] == "p2"
    resumed = client.post(f"/api/v1/series/{body['id']}/resume")
    assert resumed.json()["state"] == "active"
    issues = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    copies = [item for item in issues if item["series_id"] == body["id"]]
    assert copies
    deleted = client.delete(f"/api/v1/series/{body['id']}")
    assert deleted.status_code == 204
    listed = client.get(f"/api/v1/projects/{project['id']}/series").json()
    assert listed == []
    remaining = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    assert {item["id"] for item in copies} <= {item["id"] for item in remaining}
    assert remaining[0]["series_id"] is None
    assert remaining[0]["former_series_title"] == "Nightly backup"
    refused = client.post(f"/api/v1/series/{body['id']}/resume")
    assert refused.status_code == 404
    missing = client.get("/api/v1/series/404")
    assert missing.status_code == 404


def test_the_series_api_stores_priority_on_spawned_copies(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "HOME", "name": "Home"},
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/series",
        json={
            "title": "Urgent backup",
            "type": "story",
            "priority": "p1",
            "spawn_mode": "calendar",
            "sprint_basis": "created_on",
            "freq": "daily",
            "starts_on": "2026-09-12",
            "look_ahead_n": 1,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["priority"] == "p1"
    copies = client.get(f"/api/v1/projects/{project['id']}/issues").json()
    spawned = [item for item in copies if item["series_id"] == body["id"]]
    assert spawned
    assert {item["priority"] for item in spawned} == {"p1"}
    patched = client.patch(
        f"/api/v1/series/{body['id']}",
        json={"priority": "p2"},
    )
    assert patched.json()["priority"] == "p2"
