from fastapi.testclient import TestClient

from keel.version import package_version


def test_root_uses_shared_chrome(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "text/html" in response.headers["content-type"]
    assert "keel-topbar" in html
    assert "keel-footer" in html
    assert 'href="/"' in html
    assert 'src="/assets/small_icon.png"' in html
    assert "/assets/brand.css" in html
    assert "position: sticky" not in html
    assert f"Keel {package_version()}" in html


def test_health_has_no_menu_bar(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert "keel-topbar" not in response.text
    assert "keel-footer" not in response.text


def test_docs_has_no_keel_menu_bar(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "keel-topbar" not in response.text
    assert "keel-footer" not in response.text


def test_brand_assets(client: TestClient) -> None:
    css = client.get("/assets/brand.css")
    assert css.status_code == 200
    assert "--keel-blue: #0068b0" in css.text.lower()
    icon = client.get("/assets/small_icon.png")
    assert icon.status_code == 200
