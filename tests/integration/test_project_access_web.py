from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.domain.access import RoleCode
from keel.services import access as access_service

ADA_PASSWORD = "ada-password-1"


def _ada(client: TestClient) -> int:
    created = client.post(
        "/api/v1/users",
        json={
            "display_name": "Ada",
            "username": "ada",
            "password": ADA_PASSWORD,
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert isinstance(user_id, int)
    return user_id


def _project(client: TestClient) -> dict[str, object]:
    created = client.post("/api/v1/projects", json={"key": "BOAT", "name": "Boat"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert isinstance(body, dict)
    return body


def _sign_in(client: TestClient, username: str, password: str) -> None:
    client.post("/logout")
    signed = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert signed.status_code == 303, signed.text


def test_project_access_is_on_the_project_and_can_open_it_to_everyone(
    client: TestClient,
    app: FastAPI,
) -> None:
    ada_id = _ada(client)
    project = _project(client)
    project_id = project["id"]
    assert isinstance(project_id, int)
    page = client.get("/projects/BOAT")
    assert page.status_code == 200
    assert 'href="/projects/BOAT/access"' in page.text
    assert 'href="/admin/access"' in page.text
    access = client.get("/projects/BOAT/access")
    assert access.status_code == 200
    assert "Everyone" in access.text
    saved = client.post(
        f"/web/projects/{project_id}/access/everyone",
        data={"role": "viewer"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == "/projects/BOAT/access"
    client.put(
        f"/api/v1/access/global/{ada_id}",
        json={
            "owner": False,
            "admin": False,
            "custom": True,
            "direct_permissions": [],
        },
    )
    _sign_in(client, "ada", ADA_PASSWORD)
    assert client.get("/projects/BOAT/access").status_code == 403
    assert 'href="/projects/BOAT/access"' not in client.get("/projects/BOAT").text
    listed = client.get("/api/v1/projects").json()
    assert [item["key"] for item in listed] == ["BOAT"]
    with app.state.session_factory() as session:
        assert access_service.everyone_role(session, project_id) is RoleCode.VIEWER


def test_a_project_owner_cannot_remove_the_last_project_owner(
    client: TestClient,
) -> None:
    ada_id = _ada(client)
    project = _project(client)
    project_id = project["id"]
    assert isinstance(project_id, int)
    made = client.post(
        f"/web/projects/{project_id}/access/{ada_id}",
        data={"role": "project_owner"},
        follow_redirects=False,
    )
    assert made.status_code == 303
    cleared = client.post(
        f"/web/projects/{project_id}/access/{_owner_id(client)}",
        data={"role": ""},
        follow_redirects=False,
    )
    assert cleared.status_code == 303
    _sign_in(client, "ada", ADA_PASSWORD)
    refused = client.post(
        f"/web/projects/{project_id}/access/{ada_id}",
        data={"role": ""},
        follow_redirects=False,
    )
    assert refused.status_code == 303
    assert "last Project Owner" in client.get(refused.headers["location"]).text


def _owner_id(client: TestClient) -> int:
    people = client.get("/api/v1/users").json()
    tester = next(person for person in people if person["display_name"] == "Tester")
    user_id = tester["id"]
    assert isinstance(user_id, int)
    return user_id
