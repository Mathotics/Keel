from fastapi.testclient import TestClient


def test_phone_layout_is_a_narrow_media_query(client: TestClient) -> None:
    css = client.get("/assets/brand.css").text
    assert "@media (max-width: 40rem)" in css
    phone = css.split("@media (max-width: 40rem)", 1)[1]
    desktop_bar = css.split(".keel-topbar {", 1)[1].split("}", 1)[0]
    desktop_footer = css.split(".keel-footer {", 1)[1].split("}", 1)[0]
    desktop_column = css.split(".keel-board__column {", 1)[1].split("}", 1)[0]

    assert "position: sticky" in desktop_bar
    assert "flex-wrap" not in desktop_bar
    assert "min-height: 100vh" in css.split(".keel-footer {", 1)[0]
    assert "flex: 1 1 0" in desktop_column
    assert "min-width: 11rem" in desktop_column
    assert "flex: 0 0 80%" not in desktop_column

    assert "flex-wrap: wrap" in phone.split(".keel-topbar {", 1)[1].split("}", 1)[0]
    assert "min-height: 0" in phone.split("html,", 1)[1].split("}", 1)[0]
    overlay_sheet = phone.split(".keel-overlay__sheet {", 1)[1].split("}", 1)[0]
    assert "min-height: calc(100dvh - 1rem)" in overlay_sheet
    assert "max-width: none" in overlay_sheet
    assert "flex: 0 0 80%" in phone
    assert "min-width: 14rem" in phone
    assert "[data-keel-board] .keel-card__fallback" in phone
    fallback = phone.split("[data-keel-board] .keel-card__fallback {", 1)[1].split(
        "}",
        1,
    )[0]
    assert "display: flex" in fallback
    assert "z-index: 2" in fallback
    assert ".keel-table-scroll" in phone
    assert (
        "overflow-x: auto"
        in phone.split(".keel-table-scroll {", 1)[1].split(
            "}",
            1,
        )[0]
    )
    assert "grid-template-columns: minmax(0, 1fr)" in phone
    assert (
        "flex: 1 1 0"
        not in phone.split(".keel-board__column {", 1)[1].split(
            "}",
            1,
        )[0]
    )
    assert "position: sticky" not in desktop_footer


def test_phone_chrome_still_shows_every_bar_control(client: TestClient) -> None:
    header = (
        client.get("/projects").text.split("<header", 1)[1].split("</header>", 1)[0]
    )
    assert "keel-topbar__home" in header
    assert "keel-topbar__nav" in header
    assert "keel-find" in header
    assert "keel-userpicker" in header
    assert 'href="/projects"' in header
    assert 'href="/create"' in header
    assert 'href="/users"' in header
    footer = (
        client.get("/projects").text.split("<footer", 1)[1].split("</footer>", 1)[0]
    )
    assert "keel-footer__copyright" in footer
    assert "keel-footer__version" in footer


def test_tables_and_board_keep_swipe_markup(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/issues",
        json={"type": "story", "title": "Ready"},
    )
    projects = client.get("/projects").text
    assert 'class="keel-table-scroll"' in projects
    assert 'class="keel-table"' in projects

    board = client.get("/projects/KEEL/board").text
    assert 'class="keel-board"' in board
    assert ">Move<" in board
    assert 'action="/web/issues/' in board
    assert 'src="/assets/js/board.js"' in board
