from keel.paths import copyright_notice
from keel.version import package_version
from keel.web.layout import html_page


def test_html_page_puts_icon_first_in_the_bar() -> None:
    html = html_page(title="T", main="<p>body</p>")
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert header.find("keel-topbar__home") < header.find("small_icon.png")
    assert 'href="/"' in header
    assert "<nav" not in header
    assert "<title>T</title>" in html
    assert "<p>body</p>" in html
    assert "brand.css" in html


def test_html_page_footer_shows_package_version() -> None:
    html = html_page(title="T", main="<p>body</p>")
    footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
    assert 'class="keel-footer"' in html
    assert f"Keel {package_version()}" in footer
    assert footer.find("keel-footer__version") < footer.find(package_version())


def test_html_page_footer_copyright_links_to_license() -> None:
    html = html_page(title="T", main="<p>body</p>")
    footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
    assert 'href="/license"' in footer
    assert copyright_notice() in footer
    assert footer.find("keel-footer__copyright") < footer.find("keel-footer__version")
