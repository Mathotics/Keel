from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.api.health import health
from keel.paths import license_text
from keel.version import package_version
from tests.integration.conftest import TEST_PASSWORD, _grant_password


@contextmanager
def _signed_in(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        _grant_password(app, "Tester", TEST_PASSWORD)
        signed = client.post(
            "/login",
            data={"username": "Tester", "password": TEST_PASSWORD},
            follow_redirects=False,
        )
        assert signed.status_code == 303
        yield client


def test_health_payload() -> None:
    assert health() == {"status": "ok"}


def test_root_renders_through_the_shared_chrome(app: FastAPI) -> None:
    with _signed_in(app) as client:
        html = client.get("/").text
    assert "Keel" in html
    assert f"Keel {package_version()}" in html
    assert "keel-topbar" in html
    assert "keel-footer" in html
    assert 'href="/license"' in html


def test_license_page_shows_full_license(app: FastAPI) -> None:
    with _signed_in(app) as client:
        html = client.get("/license").text
    assert license_text().splitlines()[0] in html
    assert "No license is granted" in html
    assert "No artificial intelligence system" in html
    assert "explicit prior written permission" in html
    assert "keel-license" in html
    assert "keel-footer" in html


def test_users_page_lists_people(app: FastAPI) -> None:
    with _signed_in(app) as client:
        html = client.get("/users").text
    assert "Tester" in html
    assert "Username" in html
