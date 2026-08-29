from fastapi.testclient import TestClient


def test_favicon(client: TestClient) -> None:
    for url in ("/favicon.ico", "/assets/favicon.ico"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert "image" in response.headers["content-type"]
        assert response.content[:4] == b"\x00\x00\x01\x00"


def test_docs_use_favicon(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "/assets/favicon.ico" in response.text
