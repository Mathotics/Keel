from keel import __version__
from keel.api.health import health
from keel.api.routes import root


def test_health_payload() -> None:
    assert health() == {"status": "ok"}


def test_root_html_includes_version() -> None:
    html = root()
    assert "Keel" in html
    assert __version__ in html
    assert "keel-topbar" in html
