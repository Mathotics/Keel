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
    for path in ("/", "/license", "/users", "/create"):
        html = client.get(path).text
        assert "keel-topbar" in html
        assert "keel-footer" in html
        assert "keel-help" in html
        assert "keel-userpicker" in html


def test_health_has_no_menu_bar(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert "keel-topbar" not in response.text
    assert "keel-footer" not in response.text


def test_docs_has_no_keel_menu_bar(client: TestClient) -> None:
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        assert response.status_code == 200
        assert "keel-topbar" not in response.text
        assert "keel-footer" not in response.text
        assert "keel-help" not in response.text


def test_topbar_controls_share_one_look(client: TestClient) -> None:
    """A link, a button and a select in the bar must be indistinguishable."""
    css = client.get("/assets/brand.css").text
    control = _rule(css, ".keel-topbar__control")
    assert "var(--keel-control-height)" in control
    assert "var(--keel-control-font-size)" in control
    assert "border-radius" in control

    header = client.get("/").text.split("<header", 1)[1].split("</header>", 1)[0]
    interactive = (
        header.count("<a ")
        + header.count("<select")
        + header.count("<button")
        + header.count("<summary")
        + header.count('<input class="keel-topbar__control"')
    )
    brand = 1  # the home icon keeps its own circular treatment
    assert header.count("keel-topbar__control") == interactive - brand
    assert 'class="keel-topbar__control" href="/users"' in header
    assert 'class="keel-topbar__control" href="/projects"' in header
    assert "keel-topbar__create" in header
    assert 'href="/create"' in header


def test_create_stands_out_in_the_recorded_palette(client: TestClient) -> None:
    css = client.get("/assets/brand.css").text
    create = _rule(css, ".keel-topbar__create")
    assert "color-mix" in create
    assert "var(--keel-white)" in create
    assert "var(--keel-blue)" in create
    hover = _rule(css, ".keel-topbar__create:hover")
    assert "var(--keel-white)" in hover


def test_section_links_sit_beside_the_logo(client: TestClient) -> None:
    """Home, sections, Find, Help, then the picker, left to right."""
    header = client.get("/").text.split("<header", 1)[1].split("</header>", 1)[0]
    assert (
        header.index("keel-topbar__home")
        < header.index("keel-topbar__nav")
        < header.index("keel-find")
        < header.index("keel-help")
        < header.index("keel-userpicker")
    )
    nav = header.split('<nav class="keel-topbar__nav"', 1)[1].split("</nav>", 1)[0]
    assert (
        nav.index('href="/projects"')
        < nav.index('href="/create"')
        < nav.index('href="/users"')
    )
    assert 'href="/projects"' in nav
    assert 'href="/create"' in nav
    assert 'href="/users"' in nav
    assert "keel-nav__fallback" in nav
    assert 'action="/web/nav/move"' in nav
    assert "Board" not in nav
    assert "Up" in nav
    assert "Down" in nav
    assert 'action="/search"' in header
    assert 'name="q"' in header
    assert "required" in header.split("keel-find", 1)[1]
    assert "keel-find__fallback" in header
    assert "keel-help" not in nav
    assert "FastAPI Docs" not in nav
    assert "Help" not in nav


def test_help_discloses_fastapi_docs_without_javascript(client: TestClient) -> None:
    header = client.get("/").text.split("<header", 1)[1].split("</header>", 1)[0]
    right = header.split('class="keel-topbar__right"', 1)[1]
    help_block = right.split("<details", 1)[1].split("</details>", 1)[0]
    opening = help_block.split(">", 1)[0]
    assert 'class="keel-help"' in opening
    assert "open" not in opening
    assert "<summary" in help_block
    assert ">Help<" in help_block
    assert 'href="/docs"' in help_block
    assert 'href="/redoc"' in help_block
    assert "FastAPI Docs" in help_block
    assert ">ReDoc<" in help_block
    assert 'target="_blank"' in help_block
    assert 'rel="noopener"' in help_block
    assert help_block.index('href="/docs"') < help_block.index('href="/redoc"')
    assert right.index("keel-help") < right.index("keel-userpicker")

    css = client.get("/assets/brand.css").text
    menu = _rule(css, ".keel-help__menu")
    assert "position: absolute" in menu
    assert "js/help" not in client.get("/").text


def test_picker_switches_on_change_but_keeps_a_button_without_js(
    client: TestClient,
) -> None:
    """The dropdown submits itself; the button is the path when the script fails."""
    html = client.get("/").text
    assert '<script src="/assets/js/userpicker.js" defer></script>' in html
    assert '<script src="/assets/js/nav.js" defer></script>' in html
    assert "keel-userpicker__fallback" in html

    script = client.get("/assets/js/userpicker.js")
    assert script.status_code == 200
    assert 'addEventListener("change"' in script.text
    assert "data-keel-js" in script.text
    assert "data-keel-autosubmit" in script.text
    assert "data-keel-range" in script.text
    assert "keel-type-select" in script.text

    css = client.get("/assets/brand.css").text
    hidden = _rule(css, "[data-keel-js] .keel-userpicker__fallback")
    assert "display: none" in hidden
    autosubmit = _rule(css, "[data-keel-js] .keel-autosubmit__fallback")
    assert "display: none" in autosubmit
    find_fallback = _rule(css, "[data-keel-js] .keel-find__fallback")
    assert "display: none" in find_fallback
    nav_fallback = _rule(css, "[data-keel-nav] .keel-nav__fallback")
    assert "display: none" in nav_fallback


def test_section_links_follow_the_nav_cookie(client: TestClient) -> None:
    client.cookies.set("keel_nav", "users.create.projects")
    nav = client.get("/projects").text.split("<nav", 1)[1].split("</nav>", 1)[0]
    assert (
        nav.index('href="/users"')
        < nav.index('href="/create"')
        < nav.index('href="/projects"')
    )


def test_moving_a_section_link_sets_the_cookie_and_returns(
    client: TestClient,
) -> None:
    moved = client.post(
        "/web/nav/move",
        data={
            "item": "create",
            "direction": "up",
            "visible": "projects,create,users",
            "next": "/projects",
        },
        follow_redirects=False,
    )
    assert moved.status_code == 303
    assert moved.headers["location"] == "/projects"
    assert client.cookies["keel_nav"].split(".")[0] == "create"

    nav = client.get("/projects").text.split("<nav", 1)[1].split("</nav>", 1)[0]
    assert nav.index('href="/create"') < nav.index('href="/projects"')


def test_reordering_visible_links_leaves_hidden_project_slots(
    client: TestClient,
) -> None:
    client.post("/api/v1/projects", json={"key": "KEEL", "name": "Keel"})
    client.post(
        "/web/nav",
        data={"order": "users,projects,create", "next": "/projects"},
        follow_redirects=False,
    )
    nav = (
        client.get("/projects/KEEL/board")
        .text.split("<nav", 1)[1]
        .split(
            "</nav>",
            1,
        )[0]
    )
    assert nav.index('href="/users"') < nav.index('href="/projects/KEEL/board"')
    assert nav.index('href="/projects/KEEL/board"') < nav.index('href="/create')
    assert nav.index('href="/projects/KEEL/sprints"') < nav.index('href="/create')


def test_nav_script_enables_drag_and_hides_the_fallback(client: TestClient) -> None:
    script = client.get("/assets/js/nav.js")
    assert script.status_code == 200
    assert "data-keel-nav" in script.text
    assert 'addEventListener("dragstart"' in script.text
    assert 'fetch("/web/nav"' in script.text
    assert "data-keel-autosubmit" not in script.text


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
