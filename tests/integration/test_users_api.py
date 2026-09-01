from fastapi.testclient import TestClient


def test_seeded_user_is_present(client: TestClient) -> None:
    users = client.get("/api/v1/users").json()
    assert [user["display_name"] for user in users] == ["Tester"]


def test_user_lifecycle(client: TestClient) -> None:
    created = client.post("/api/v1/users", json={"display_name": "Ada"})
    assert created.status_code == 201
    user_id = created.json()["id"]

    assert client.get(f"/api/v1/users/{user_id}").json()["display_name"] == "Ada"

    renamed = client.patch(
        f"/api/v1/users/{user_id}",
        json={"display_name": "Ada Lovelace"},
    )
    assert renamed.json()["display_name"] == "Ada Lovelace"

    assert client.delete(f"/api/v1/users/{user_id}").status_code == 204
    assert client.get(f"/api/v1/users/{user_id}").status_code == 404


def test_duplicate_name_returns_a_coded_conflict(client: TestClient) -> None:
    client.post("/api/v1/users", json={"display_name": "Ada"})
    conflict = client.post("/api/v1/users", json={"display_name": "Ada"})
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["code"] == "user.duplicate_name"
    assert detail["context"] == {"display_name": "Ada"}


def test_blank_name_is_rejected_by_validation(client: TestClient) -> None:
    assert client.post("/api/v1/users", json={"display_name": ""}).status_code == 422


def test_missing_user_returns_not_found(client: TestClient) -> None:
    renamed = client.patch("/api/v1/users/404", json={"display_name": "X"})
    assert renamed.status_code == 404
    assert client.delete("/api/v1/users/404").status_code == 404


def test_openapi_documents_the_versioned_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/users" in paths
    assert "/api/v1/users/{user_id}" in paths
