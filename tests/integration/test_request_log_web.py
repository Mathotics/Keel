import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD
from tests.integration.test_issues_api import create_issue


def test_signed_out_visitors_go_to_login(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/admin/log", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_empty_log_and_admin_menu(client: TestClient) -> None:
    response = client.get("/admin/log")
    assert response.status_code == 200
    assert "No requests yet." in response.text
    assert ">Log tracker<" in response.text
    header = response.text.split("<header", 1)[1].split("</header>", 1)[0]
    assert header.index("keel-admin") < header.index("keel-help")


def test_log_records_requests_and_hides_noise(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/assets/brand.css").status_code == 200
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/projects?secret=hide-me").status_code == 200
    missing = client.get("/api/v1/issues/999999")
    assert missing.status_code == 404

    html = client.get("/admin/log").text
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert "GET" in body
    assert "/projects" in body
    assert "/health" not in body
    assert "brand.css" not in body
    assert "favicon" not in body
    assert "/admin/log" not in body
    assert "hide-me" not in html
    assert "secret" not in html
    assert "/api/v1/issues/999999" in body
    assert ">404<" in body


def test_filters_combine(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    )
    assert project.status_code == 201
    issue = create_issue(client, project.json()["id"])
    updated = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200
    failed = client.post(
        f"/api/v1/projects/{project.json()['id']}/issues",
        json={"type": "nope", "title": "Bad"},
    )
    assert failed.status_code == 422

    changes = _tbody(client.get("/admin/log?kind=changes").text)
    assert "KEEL-1 status To Do → In Progress" in changes
    assert "project KEEL created" in changes
    assert "<td>GET</td>" not in changes

    succeeded = _tbody(client.get("/admin/log?kind=changes&result=succeeded").text)
    assert "KEEL-1 status To Do → In Progress" in succeeded
    assert ">422<" not in succeeded

    failed_only = _tbody(client.get("/admin/log?result=failed").text)
    assert ">422<" in failed_only
    assert "KEEL-1 created" not in failed_only

    path = _tbody(client.get("/admin/log?path=/api/v1/issues").text)
    assert "/api/v1/issues" in path
    assert "project KEEL created" not in path

    today = client.get("/admin/log?span=today&kind=changes").text
    assert "KEEL-1 status To Do → In Progress" in _tbody(today)
    assert "<strong>Today</strong>" in today

    ada = client.post(
        "/api/v1/users",
        json={"display_name": "Ada", "password": TEST_PASSWORD},
    ).json()
    client.post(
        "/login",
        data={"username": "Ada", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert client.get("/license").status_code == 200
    client.post(
        "/login",
        data={"username": "Tester", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    ada_only = _tbody(client.get(f"/admin/log?person={ada['id']}").text)
    assert "/license" in ada_only
    assert "Ada" in ada_only
    assert "project KEEL created" not in ada_only


def test_pages_move_through_older_rows(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("keel.services.request_log.PAGE_SIZE", 1)
    assert client.get("/projects").status_code == 200
    assert client.get("/users").status_code == 200
    first = client.get("/admin/log")
    assert "Older" in first.text
    assert "/users" in _tbody(first.text)
    second = client.get("/admin/log?page=2")
    assert "Newer" in second.text
    assert "/projects" in _tbody(second.text)


def test_password_change_does_not_store_the_secret(client: TestClient) -> None:
    response = client.post(
        "/web/profile/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": "another-password-1",
            "confirm_password": "another-password-1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    html = client.get("/admin/log?kind=changes").text
    assert "password changed" in html
    assert "another-password-1" not in html
    assert "argon" not in html


def test_no_match_copy(client: TestClient) -> None:
    assert client.get("/projects").status_code == 200
    html = client.get("/admin/log?path=/does-not-exist").text
    assert "No requests match." in html


def _tbody(html: str) -> str:
    return html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
