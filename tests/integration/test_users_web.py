from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD


def test_users_page_shows_the_seeded_user(client: TestClient) -> None:
    page = client.get("/users")
    assert page.status_code == 200
    assert "Tester" in page.text


def test_add_rename_and_delete_through_forms(client: TestClient) -> None:
    added = client.post(
        "/web/users",
        data={
            "display_name": "Ada",
            "password": TEST_PASSWORD,
            "confirm": TEST_PASSWORD,
        },
    )
    assert added.status_code == 200
    assert added.url.path == "/users"
    assert "Ada" in added.text

    user_id = _id_of(client, "Ada")
    renamed = client.post(
        f"/web/users/{user_id}/rename",
        data={"display_name": "Ada Lovelace"},
    )
    assert "Ada Lovelace" in renamed.text

    deleted = client.post(f"/web/users/{user_id}/delete")
    assert "Ada Lovelace" not in deleted.text


def test_duplicate_name_shows_a_message_on_the_page(client: TestClient) -> None:
    client.post(
        "/web/users",
        data={
            "display_name": "Ada",
            "password": TEST_PASSWORD,
            "confirm": TEST_PASSWORD,
        },
    )
    refused = client.post(
        "/web/users",
        data={
            "display_name": "Ada",
            "password": TEST_PASSWORD,
            "confirm": TEST_PASSWORD,
        },
    )
    assert refused.status_code == 200
    assert "already taken" in refused.text


def test_blank_name_shows_a_message_on_the_page(client: TestClient) -> None:
    refused = client.post("/web/users", data={"display_name": "  "})
    assert "needs a display name" in refused.text


def test_renaming_to_a_taken_name_shows_a_message(client: TestClient) -> None:
    client.post(
        "/web/users",
        data={
            "display_name": "Ada",
            "password": TEST_PASSWORD,
            "confirm": TEST_PASSWORD,
        },
    )
    tester = _id_of(client, "Tester")
    refused = client.post(
        f"/web/users/{tester}/rename",
        data={"display_name": "Ada"},
    )
    assert "already taken" in refused.text


def test_deleting_a_user_still_named_on_an_issue_shows_a_message(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects", json={"key": "KEEL", "name": "Keel"}
    ).json()
    added = client.post(
        "/web/users",
        data={
            "display_name": "Ada",
            "password": TEST_PASSWORD,
            "confirm": TEST_PASSWORD,
        },
    )
    assert added.status_code == 200
    ada = _id_of(client, "Ada")
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Work", "assignee_id": ada},
    )
    refused = client.post(f"/web/users/{ada}/delete")
    assert "still named" in refused.text


def test_deleting_someone_who_is_gone_shows_no_crash(client: TestClient) -> None:
    assert client.post("/web/users/404/delete").status_code == 404


def test_the_signed_in_person_cannot_delete_themselves(client: TestClient) -> None:
    tester = _id_of(client, "Tester")
    refused = client.post(f"/web/users/{tester}/delete")
    assert "someone else" in refused.text
    assert "Tester" in client.get("/users").text


def _id_of(client: TestClient, name: str) -> int:
    users = client.get("/api/v1/users").json()
    return int(next(user["id"] for user in users if user["display_name"] == name))
