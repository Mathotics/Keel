from keel.web.layout import html_page


def test_html_page_puts_icon_first_in_the_bar() -> None:
    html = html_page(title="T", main="<p>body</p>")
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert header.find("keel-topbar__home") < header.find("small_icon.png")
    assert 'href="/"' in header
    assert "<nav" not in header
