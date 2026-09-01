from fastapi.testclient import TestClient

from keel.web.context import USER_COOKIE


def test_users_page_shows_the_seeded_user(client: TestClient) -> None:
    page = client.get("/users")
    assert page.status_code == 200
    assert "Tester" in page.text


def test_add_rename_and_delete_through_forms(client: TestClient) -> None:
    added = client.post("/web/users", data={"display_name": "Ada"})
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
    client.post("/web/users", data={"display_name": "Ada"})
    refused = client.post("/web/users", data={"display_name": "Ada"})
    assert refused.status_code == 200
    assert "already taken" in refused.text


def test_blank_name_shows_a_message_on_the_page(client: TestClient) -> None:
    refused = client.post("/web/users", data={"display_name": "  "})
    assert "needs a display name" in refused.text


def test_deleting_someone_who_is_gone_shows_no_crash(client: TestClient) -> None:
    assert client.post("/web/users/404/delete").status_code == 404


def test_picker_sets_the_cookie_and_returns_to_the_page(client: TestClient) -> None:
    client.post("/web/users", data={"display_name": "Ada"})
    ada = _id_of(client, "Ada")

    switched = client.post(
        "/web/user",
        data={"user": str(ada), "next": "/users"},
        follow_redirects=False,
    )
    assert switched.status_code == 303
    assert switched.headers["location"] == "/users"
    assert client.cookies[USER_COOKIE] == str(ada)


def _id_of(client: TestClient, name: str) -> int:
    users = client.get("/api/v1/users").json()
    return int(next(user["id"] for user in users if user["display_name"] == name))
