from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.services import users as user_service
from keel.services.identity import SESSION_COOKIE
from keel.services.recovery import INVALID_LINK, LOOKUP_NOTICE, RESET_NOTICE
from tests.integration.conftest import TEST_PASSWORD


def _set_email(app: FastAPI, username: str, email: str) -> None:
    with app.state.session_factory() as session:
        user = user_service.find_by_username(session, username)
        assert user is not None
        user.email = email
        session.commit()


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []

    def send(to: str, subject: str, body: str) -> None:
        sent.append((to, subject, body))

    monkeypatch.setattr("keel.services.mail.send", send)
    return sent


def _token(body: str) -> str:
    start = body.index("http")
    link = body[start:].split()[0]
    return parse_qs(urlparse(link).query)["token"][0]


def test_unknown_username_and_blank_email_show_the_same_notice(
    app: FastAPI,
    anonymous_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    unknown = anonymous_client.post(
        "/forgot-password",
        data={"username": "missing"},
        follow_redirects=False,
    )
    assert unknown.status_code == 303
    page = anonymous_client.get(unknown.headers["location"])
    assert RESET_NOTICE in page.text
    assert not sent

    _set_email(app, "Tester", "")
    blank = anonymous_client.post(
        "/api/v1/password-resets",
        json={"username": "Tester"},
    )
    assert blank.status_code == 200
    assert blank.json() == {"notice": RESET_NOTICE}
    assert not sent

    empty = anonymous_client.post("/api/v1/password-resets", json={"username": " "})
    assert empty.status_code == 422
    assert empty.json()["detail"] == "Enter a username."


def test_reset_signs_this_browser_in_and_ends_other_sessions(
    app: FastAPI,
    anonymous_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    _set_email(app, "Tester", "tester@example.com")
    signed = anonymous_client.post(
        "/login",
        data={"username": "Tester", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    old_cookie = signed.cookies.get(SESSION_COOKIE)
    assert old_cookie
    issued = anonymous_client.post(
        "/api/v1/profile/tokens",
        json={"label": "phone"},
    )
    assert issued.status_code == 201
    secret = issued.json()["token"]

    requested = anonymous_client.post(
        "/forgot-password",
        data={"username": "tester"},
        follow_redirects=False,
    )
    assert RESET_NOTICE in anonymous_client.get(requested.headers["location"]).text
    assert sent[0][0] == "tester@example.com"
    assert "Tester" in sent[0][2]
    assert "/reset-password?token=" in sent[0][2]
    token = _token(sent[0][2])

    mismatch = anonymous_client.post(
        "/reset-password",
        data={
            "token": token,
            "new_password": "a-brand-new-secret",
            "confirm_password": "different-secret-1",
        },
        follow_redirects=False,
    )
    assert mismatch.status_code == 303
    retry = anonymous_client.get(mismatch.headers["location"])
    assert "do not match" in retry.text
    assert 'name="token"' in retry.text

    saved = anonymous_client.post(
        "/reset-password",
        data={
            "token": token,
            "new_password": "a-brand-new-secret",
            "confirm_password": "a-brand-new-secret",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == "/"
    assert anonymous_client.get("/").status_code == 200

    anonymous_client.cookies.delete(SESSION_COOKIE)
    anonymous_client.cookies.set(SESSION_COOKIE, old_cookie, domain="testserver")
    assert anonymous_client.get("/", follow_redirects=False).status_code == 303

    still = anonymous_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert still.status_code == 200

    again = anonymous_client.get(f"/reset-password?token={token}")
    assert INVALID_LINK in again.text
    assert "Request a new link" in again.text


def test_a_newer_reset_cancels_the_previous_link(
    app: FastAPI,
    anonymous_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    _set_email(app, "Tester", "tester@example.com")
    anonymous_client.post(
        "/api/v1/password-resets",
        json={"username": "Tester"},
    )
    anonymous_client.post(
        "/api/v1/password-resets",
        json={"username": "Tester"},
    )
    assert len(sent) == 2
    first = _token(sent[0][2])
    second = _token(sent[1][2])
    dead = anonymous_client.get(f"/reset-password?token={first}")
    assert INVALID_LINK in dead.text
    live = anonymous_client.get(f"/reset-password?token={second}")
    assert 'name="new_password"' in live.text


def test_username_lookup_emails_the_name_and_hides_it_on_the_page(
    app: FastAPI,
    anonymous_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    _set_email(app, "Tester", "Tester@Example.com")
    found = anonymous_client.post(
        "/forgot-username",
        data={"email": "tester@example.com"},
        follow_redirects=False,
    )
    page = anonymous_client.get(found.headers["location"])
    assert LOOKUP_NOTICE in page.text
    assert ">Tester<" not in page.text
    assert sent == [
        (
            "Tester@Example.com",
            "Your Keel username",
            "Your Keel username is Tester.\n",
        ),
    ]

    missing = anonymous_client.post(
        "/api/v1/username-lookups",
        json={"email": "nobody@example.com"},
    )
    assert missing.json() == {"notice": LOOKUP_NOTICE}
    assert len(sent) == 1

    blank = anonymous_client.post("/api/v1/username-lookups", json={"email": " "})
    assert blank.status_code == 422


def test_duplicate_email_is_refused_on_the_profile(client: TestClient) -> None:
    me = client.get("/api/v1/profile").json()
    first = client.patch(
        "/api/v1/profile",
        json={
            "display_name": me["display_name"],
            "username": me["username"],
            "email": "shared@example.com",
        },
    )
    assert first.status_code == 200
    created = client.post(
        "/api/v1/users",
        json={
            "display_name": "Ada",
            "password": TEST_PASSWORD,
            "email": "ada@example.com",
        },
    )
    assert created.status_code == 201
    ada_id = created.json()["id"]
    client.post("/logout", follow_redirects=False)
    client.post(
        "/login",
        data={"username": "Ada", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    taken = client.patch(
        "/api/v1/profile",
        json={
            "display_name": "Ada",
            "username": "Ada",
            "email": "Shared@Example.com",
        },
    )
    assert taken.status_code == 422
    assert taken.json()["detail"]["code"] == "user.email_taken"
    assert client.get("/api/v1/profile").json()["id"] == ada_id
