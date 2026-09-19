from keel.web.inbox import encode_collapsed, encode_toggle, parse_collapsed


def test_a_blank_cookie_means_every_section_is_open() -> None:
    assert parse_collapsed(None) == frozenset()
    assert parse_collapsed("") == frozenset()
    assert encode_collapsed(()) == ""


def test_unknown_keys_are_dropped_and_order_is_canonical() -> None:
    parsed = parse_collapsed("waiting,nope,assigned.due.completed")
    assert parsed == frozenset({"waiting", "assigned", "due", "completed"})
    assert encode_collapsed(parsed) == "due.assigned.waiting.completed"


def test_toggling_a_section_adds_or_removes_it() -> None:
    assert encode_toggle((), "assigned") == "assigned"
    assert encode_toggle(("assigned", "blocked"), "assigned") == "blocked"
    assert encode_toggle(("blocked",), "nope") == "blocked"
