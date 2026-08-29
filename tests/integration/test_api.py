from fastapi.testclient import TestClient

from keel import __version__


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
    assert __version__ in response.text
    assert "keel-topbar" in response.text
