from keel.api.health import health
from keel.api.routes import root
from keel.version import package_version


def test_health_payload() -> None:
    assert health() == {"status": "ok"}


def test_root_html_includes_version() -> None:
    html = root()
    assert "Keel" in html
    assert f"Keel {package_version()}" in html
    assert "keel-topbar" in html
    assert "keel-footer" in html
