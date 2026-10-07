from keel.web.issue_panels import encode_collapsed, encode_toggle, parse_collapsed


def test_a_blank_cookie_means_every_panel_is_open() -> None:
    assert parse_collapsed(None) == frozenset()
    assert parse_collapsed("") == frozenset()
    assert encode_collapsed(()) == ""


def test_unknown_keys_are_dropped_and_order_is_canonical() -> None:
    parsed = parse_collapsed("comments,nope,history.description.due")
    assert parsed == frozenset({"comments", "history", "description"})
    assert encode_collapsed(parsed) == "description.history.comments"


def test_toggling_a_panel_adds_or_removes_it() -> None:
    assert encode_toggle((), "comments") == "comments"
    assert encode_toggle(("comments", "history"), "comments") == "history"
    assert encode_toggle(("history",), "nope") == "history"
