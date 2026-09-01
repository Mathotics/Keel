import pytest
from fastapi.testclient import TestClient

ASSETS = ("/assets/brand.css", "/assets/js/userpicker.js", "/assets/js/board.js")


@pytest.mark.parametrize("url", ASSETS)
def test_assets_are_served(client: TestClient, url: str) -> None:
    response = client.get(url)
    assert response.status_code == 200
    assert response.content


@pytest.mark.parametrize("url", ASSETS)
def test_assets_must_be_revalidated(client: TestClient, url: str) -> None:
    """Without this the browser may serve a stale stylesheet after an edit."""
    response = client.get(url)
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("url", ASSETS)
def test_an_unchanged_asset_revalidates_cheaply(client: TestClient, url: str) -> None:
    etag = client.get(url).headers["etag"]

    response = client.get(url, headers={"If-None-Match": etag})
    assert response.status_code == 304
