from keel.web.board_lanes import (
    BoardLanes,
    encode_keys,
    encode_toggle,
    hide_lane,
    lane_key,
    merge_collapsed,
    parse_keys,
    parse_lanes,
    show_lane,
)


def test_a_blank_cookie_means_every_sprint_row_is_open_and_shown() -> None:
    assert parse_lanes(None, None) == BoardLanes(frozenset(), frozenset())
    assert parse_lanes("", "") == BoardLanes(frozenset(), frozenset())
    assert encode_keys(()) == ""


def test_lane_keys_distinguish_a_sprint_from_each_unscheduled_row() -> None:
    assert lane_key(12, project_id=3) == "12"
    assert lane_key(None, project_id=3) == "unscheduled-3"
    assert lane_key(None, project_id=None) == "unscheduled"


def test_unknown_keys_are_dropped_and_order_is_numeric() -> None:
    parsed = parse_keys("10,nope,2.unscheduled.01.0.unscheduled-0.unscheduled-3")
    assert parsed == frozenset({"10", "2", "unscheduled", "unscheduled-3"})
    assert encode_keys(parsed) == "2.10.unscheduled.unscheduled-3"


def test_toggling_a_row_adds_or_removes_it() -> None:
    assert encode_toggle((), "12") == "12"
    assert encode_toggle(("12", "unscheduled"), "12") == "unscheduled"
    assert encode_toggle(("12",), "nope") == "12"


def test_a_page_posts_only_the_rows_it_is_showing() -> None:
    current = frozenset({"9", "2"})
    assert merge_collapsed(current, "2", "2.unscheduled") == frozenset({"9", "2"})
    assert merge_collapsed(current, "", "2.unscheduled") == frozenset({"9"})
    assert merge_collapsed(current, "unscheduled", None) == frozenset({"unscheduled"})


def test_hiding_and_showing_a_row_ignores_unknown_keys() -> None:
    assert encode_keys(hide_lane((), "12")) == "12"
    assert encode_keys(hide_lane(("12",), "12")) == "12"
    assert encode_keys(hide_lane(("12",), "nope")) == "12"
    assert encode_keys(show_lane(("12", "unscheduled"), "12")) == "unscheduled"


def test_each_cookie_keeps_at_most_two_hundred_keys() -> None:
    raw = ".".join(str(number) for number in range(1, 203))
    assert len(parse_keys(raw)) == 200
    assert "201" not in parse_keys(raw)
