from keel.web.home_layout import (
    apply_move,
    apply_posted_order,
    default_layout,
    encode_layout,
    hide_panel,
    parse_layout,
    show_panel,
)
from keel.web.inbox import SECTIONS


def test_a_missing_cookie_is_the_default_stack() -> None:
    layout = parse_layout(None)
    assert layout == default_layout()
    assert layout.order == SECTIONS
    assert layout.hidden == frozenset()
    assert encode_layout(layout) == f"{'.'.join(SECTIONS)}/"


def test_unknown_keys_are_dropped_and_new_panels_stay_visible() -> None:
    layout = parse_layout("assigned.nope.due/upcoming.blocked")
    assert layout.hidden == frozenset({"blocked"})
    assert layout.order[0] == "assigned"
    assert layout.order[1] == "due"
    assert "blocked" not in layout.order
    assert "week" in layout.order


def test_hide_and_show_round_trip() -> None:
    hidden = hide_panel(default_layout(), "assigned")
    assert "assigned" not in hidden.order
    assert hidden.hidden == frozenset({"assigned"})
    shown = show_panel(hidden, "assigned")
    assert shown.hidden == frozenset()
    assert shown.order[-1] == "assigned"
    assert hide_panel(hidden, "nope") == hidden


def test_move_swaps_neighbours_and_keeps_empty_slots() -> None:
    moved = apply_move(
        default_layout(),
        ["due", "assigned"],
        "assigned",
        "up",
    )
    assert moved.order[0] == "assigned"
    assert moved.order[1] == "week"
    assert moved.order[4] == "due"


def test_posted_order_replaces_only_the_panels_on_the_page() -> None:
    posted = apply_posted_order(default_layout(), ["assigned", "due"])
    assert posted.order[0] == "assigned"
    assert posted.order[4] == "due"
    assert apply_posted_order(default_layout(), ["nope"]) == default_layout()
