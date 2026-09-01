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
    assert 'href="/license"' in html


def test_chrome_carries_the_user_picker(client: TestClient) -> None:
    html = client.get("/").text
    assert 'action="/web/user"' in html
    assert "keel-userpicker" in html
    assert "Tester" in html
    assert 'href="/users"' in html


def test_every_page_shares_the_same_chrome(client: TestClient) -> None:
    for path in ("/", "/license", "/users"):
        html = client.get(path).text
        assert "keel-topbar" in html
        assert "keel-footer" in html
        assert "keel-userpicker" in html


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


def test_topbar_controls_share_one_look(client: TestClient) -> None:
    """A link, a button and a select in the bar must be indistinguishable."""
    css = client.get("/assets/brand.css").text
    control = _rule(css, ".keel-topbar__control")
    assert "var(--keel-control-height)" in control
    assert "var(--keel-control-font-size)" in control
    assert "border-radius" in control

    header = client.get("/").text.split("<header", 1)[1].split("</header>", 1)[0]
    assert header.count("keel-topbar__control") == 3
    assert '<a class="keel-topbar__control" href="/users">' in header


def test_section_links_sit_beside_the_logo(client: TestClient) -> None:
    """Sections read left to right from the logo; the picker stays at the far end."""
    header = client.get("/").text.split("<header", 1)[1].split("</header>", 1)[0]
    assert (
        header.index("keel-topbar__home")
        < header.index("keel-topbar__nav")
        < header.index("keel-userpicker")
    )
    nav = header.split('<nav class="keel-topbar__nav"', 1)[1].split("</nav>", 1)[0]
    assert 'href="/users"' in nav


def test_picker_switches_on_change_but_keeps_a_button_without_js(
    client: TestClient,
) -> None:
    """The dropdown submits itself; the button is the path when the script fails."""
    html = client.get("/").text
    assert '<script src="/assets/js/userpicker.js" defer></script>' in html
    assert "keel-userpicker__fallback" in html

    script = client.get("/assets/js/userpicker.js")
    assert script.status_code == 200
    assert 'addEventListener("change"' in script.text
    assert "data-keel-js" in script.text

    css = client.get("/assets/brand.css").text
    hidden = _rule(css, "[data-keel-js] .keel-userpicker__fallback")
    assert "display: none" in hidden


def test_topbar_label_matches_the_control_height(client: TestClient) -> None:
    """Centring boxes of different heights still looks ragged, so they must match."""
    label = _rule(client.get("/assets/brand.css").text, ".keel-userpicker__label")
    assert "var(--keel-control-height)" in label
    assert "var(--keel-control-font-size)" in label


def _rule(css: str, selector: str) -> str:
    return css.split(selector, 1)[1].split("{", 1)[1].split("}", 1)[0]


def test_brand_assets(client: TestClient) -> None:
    css = client.get("/assets/brand.css")
    assert css.status_code == 200
    text = css.text.lower()
    assert "--keel-blue: #0068b0" in text
    assert "min-height: 100vh" in text
    footer_block = text.split(".keel-footer {", 1)[1].split("}", 1)[0]
    topbar_block = text.split(".keel-topbar {", 1)[1].split("}", 1)[0]
    assert "var(--keel-sheet)" in footer_block
    assert "var(--keel-blue)" in topbar_block
    assert "var(--keel-sheet)" not in topbar_block
    icon = client.get("/assets/small_icon.png")
    assert icon.status_code == 200
