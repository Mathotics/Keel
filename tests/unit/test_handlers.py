from keel.api.health import health
from keel.api.routes import license_page, root
from keel.paths import license_text
from keel.version import package_version


def test_health_payload() -> None:
    assert health() == {"status": "ok"}


def test_root_html_includes_version() -> None:
    html = root()
    assert "Keel" in html
    assert f"Keel {package_version()}" in html
    assert "keel-topbar" in html
    assert "keel-footer" in html
    assert 'href="/license"' in html


def test_license_page_shows_full_license() -> None:
    html = license_page()
    assert license_text().splitlines()[0] in html
    assert "No license is granted" in html
    assert "keel-license" in html
    assert "keel-footer" in html
