from fastapi import FastAPI
from fastapi.testclient import TestClient

from keel.api.health import health
from keel.paths import license_text
from keel.version import package_version


def test_health_payload() -> None:
    assert health() == {"status": "ok"}


def test_root_renders_through_the_shared_chrome(app: FastAPI) -> None:
    html = TestClient(app).get("/").text
    assert "Keel" in html
    assert f"Keel {package_version()}" in html
    assert "keel-topbar" in html
    assert "keel-footer" in html
    assert 'href="/license"' in html


def test_license_page_shows_full_license(app: FastAPI) -> None:
    html = TestClient(app).get("/license").text
    assert license_text().splitlines()[0] in html
    assert "No license is granted" in html
    assert "keel-license" in html
    assert "keel-footer" in html


def test_users_page_lists_people(app: FastAPI) -> None:
    with TestClient(app) as client:
        html = client.get("/users").text
    assert "Tester" in html
    assert "Identity is declared, not verified" in html
