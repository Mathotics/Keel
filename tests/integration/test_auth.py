from urllib.parse import unquote

from fastapi.testclient import TestClient

from tests.integration.conftest import TEST_PASSWORD


def test_anonymous_pages_redirect_to_login(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/projects", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_anonymous_api_is_unauthorized(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/api/v1/users")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in."


def test_health_and_assets_stay_public(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/health").json() == {"status": "ok"}
    assert anonymous_client.get("/assets/brand.css").status_code == 200


def test_a_declared_header_does_not_sign_anyone_in(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.get(
        "/api/v1/users",
        headers={"X-Keel-User": "Tester"},
    )
    assert response.status_code == 401


def test_login_then_profile_then_logout(anonymous_client: TestClient) -> None:
    refused = anonymous_client.post(
        "/login",
        data={"username": "Tester", "password": "not-the-password"},
        follow_redirects=False,
    )
    assert refused.status_code == 303
    assert "not recognized" in unquote(refused.headers["location"])

    signed = anonymous_client.post(
        "/login",
        data={"username": "tester", "password": TEST_PASSWORD, "next": "/profile"},
        follow_redirects=False,
    )
    assert signed.status_code == 303
    assert signed.headers["location"] == "/profile"

    page = anonymous_client.get("/profile")
    assert page.status_code == 200
    assert "Tester" in page.text
    assert "API tokens" in page.text

    renamed = anonymous_client.post(
        "/web/profile",
        data={"display_name": "Tess", "username": "Tester"},
    )
    assert "Profile updated." in renamed.text
    assert "Tess" in renamed.text

    changed = anonymous_client.post(
        "/web/profile/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": "a-new-secret-1",
            "confirm_password": "a-new-secret-1",
        },
    )
    assert "Password updated." in changed.text

    issued = anonymous_client.post(
        "/web/profile/tokens",
        data={"label": "Cursor agent"},
        follow_redirects=False,
    )
    assert issued.status_code == 303
    shown = anonymous_client.get("/profile")
    secret = _full_token(shown.text)
    again = anonymous_client.get("/profile")
    assert secret not in again.text
    assert secret[:12] in again.text

    anonymous_client.post("/logout", follow_redirects=False)
    home = anonymous_client.get("/", follow_redirects=False)
    assert home.status_code == 303


def _full_token(html: str) -> str:
    import re

    match = re.search(r"keel_[A-Za-z0-9_-]{20,}", html)
    assert match is not None
    return match.group(0)


def test_an_api_token_acts_as_that_person(client: TestClient) -> None:
    created = client.post(
        "/api/v1/profile/tokens",
        json={"label": "script"},
    )
    assert created.status_code == 201
    secret = created.json()["token"]
    assert secret.startswith("keel_")
    assert "token" not in client.get("/api/v1/profile/tokens").json()[0]

    client.post("/logout", follow_redirects=False)
    listed = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert listed.status_code == 200
    assert any(user["display_name"] == "Tester" for user in listed.json())


def test_login_refuses_an_off_site_next(anonymous_client: TestClient) -> None:
    signed = anonymous_client.post(
        "/login",
        data={
            "username": "Tester",
            "password": TEST_PASSWORD,
            "next": "https://evil.example/phish",
        },
        follow_redirects=False,
    )
    assert signed.headers["location"] == "/"
