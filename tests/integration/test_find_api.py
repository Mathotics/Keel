from fastapi.testclient import TestClient


def test_search_jumps_to_an_exact_issue_key_and_lists_other_matches(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects", json={"key": "FIND", "name": "Find"}
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Paint the door"},
    ).json()

    jump = client.get("/api/v1/search", params={"q": "find-1"})
    assert jump.status_code == 200
    body = jump.json()
    assert body["kind"] == "jump"
    assert body["target"] == "issue"
    assert body["issue_id"] == issue["id"]
    assert body["key"] == "FIND-1"

    listed = client.get("/api/v1/search", params={"q": "door"})
    assert listed.status_code == 200
    matches = listed.json()
    assert matches["kind"] == "results"
    assert matches["issues"][0]["id"] == issue["id"]
    assert matches["issues"][0]["key"] == "FIND-1"
    assert matches["empty"] is False
