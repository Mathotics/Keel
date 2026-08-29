from fastapi.testclient import TestClient

from keel.paths import license_text
from keel.version import package_version


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Keel" in response.text
    assert "/assets/favicon.ico" in response.text
    assert f"Keel {package_version()}" in response.text
    assert "keel-topbar" in response.text
    assert "keel-footer" in response.text
    assert 'href="/license"' in response.text


def test_license_page(client: TestClient) -> None:
    response = client.get("/license")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert license_text().strip()[:40] in response.text
    assert "keel-topbar" in response.text
    assert "keel-footer" in response.text
