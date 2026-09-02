from markupsafe import Markup

from keel.web.markdown import render_markdown


def test_emphasis_and_a_list_become_html() -> None:
    html = str(render_markdown("A **bold** note\n\n- one\n- two"))
    assert "<strong>bold</strong>" in html
    assert "<li>one</li>" in html
    assert isinstance(render_markdown("A **bold** note"), Markup)


def test_a_line_break_in_plain_text_is_kept() -> None:
    html = str(render_markdown("first line\nsecond line"))
    assert "<br" in html
    assert "first line" in html
    assert "second line" in html


def test_empty_source_renders_nothing() -> None:
    assert str(render_markdown("")) == ""
    assert str(render_markdown("   ")) == ""


def test_script_and_javascript_urls_are_stripped() -> None:
    html = str(
        render_markdown(
            "<script>alert(1)</script>\n[bad](javascript:alert(1))\n[ok](https://example.com)",
        ),
    )
    assert "<script" not in html.lower()
    assert "javascript:" not in html.lower()
    assert 'href="https://example.com"' in html


def test_a_bare_url_is_linked() -> None:
    html = str(render_markdown("See https://example.com/docs for more."))
    assert 'href="https://example.com/docs"' in html


def test_fenced_code_and_a_table_become_html() -> None:
    html = str(
        render_markdown(
            "```\nprint(1)\n```\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n",
        ),
    )
    assert "<pre>" in html
    assert "<code>" in html
    assert "print(1)" in html
    assert "<table>" in html
    assert "<th>a</th>" in html
    assert "<td>1</td>" in html


def test_event_handlers_are_stripped() -> None:
    html = str(
        render_markdown('<p onclick="alert(1)">ok</p><img src="x" onerror="alert(1)">'),
    )
    assert "onclick" not in html.lower()
    assert "onerror" not in html.lower()
    assert "<img" not in html.lower()
    assert "ok" in html
