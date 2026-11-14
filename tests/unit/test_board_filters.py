from keel.web.board_filters import encode_collapsed, encode_toggle, parse_collapsed


def test_a_blank_cookie_means_the_filter_bar_is_open() -> None:
    assert parse_collapsed(None) == frozenset()
    assert parse_collapsed("") == frozenset()
    assert encode_collapsed(()) == ""


def test_unknown_keys_are_dropped() -> None:
    parsed = parse_collapsed("nope,filters.lanes")
    assert parsed == frozenset({"filters"})
    assert encode_collapsed(parsed) == "filters"


def test_toggling_the_filter_bar_adds_or_removes_it() -> None:
    assert encode_toggle((), "filters") == "filters"
    assert encode_toggle(("filters",), "filters") == ""
    assert encode_toggle(("filters",), "nope") == "filters"
