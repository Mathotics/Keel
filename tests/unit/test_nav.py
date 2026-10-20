from keel.web.nav import encode_order, links_for, merge_visible, move_item, parse_order


def test_a_blank_cookie_is_the_default_order() -> None:
    assert parse_order(None)[0] == "projects"
    assert parse_order("")[-1] == "schedules"
    assert "create" in parse_order(None)


def test_unknown_keys_are_dropped_and_missing_defaults_are_appended() -> None:
    parsed = parse_order("schedules,nope,create")
    assert parsed[0] == "schedules"
    assert "nope" not in parsed
    assert set(parse_order("schedules")) == {
        "projects",
        "create",
        "board",
        "calendar",
        "backlog",
        "sprints",
        "schedules",
    }


def test_merging_visible_items_leaves_hidden_ones_in_place() -> None:
    full = parse_order(None)
    merged = merge_visible(full, ["projects", "schedules", "create"])
    assert [key for key in merged if key in {"projects", "create", "schedules"}] == [
        "projects",
        "schedules",
        "create",
    ]
    assert merged.index("board") < merged.index("backlog") < merged.index("sprints")


def test_moving_up_swaps_with_the_previous_visible_item() -> None:
    assert move_item(["projects", "create", "schedules"], "create", "up") == (
        "create",
        "projects",
        "schedules",
    )


def test_moving_past_the_end_does_nothing() -> None:
    shown = ("projects", "create", "schedules")
    assert move_item(shown, "projects", "up") == shown
    assert move_item(shown, "schedules", "down") == shown
    assert move_item(shown, "create", "sideways") == shown
    assert move_item(shown, "board", "up") == shown


def test_an_empty_visible_list_leaves_the_full_order_alone() -> None:
    full = parse_order(None)
    assert merge_visible(full, []) == full


def test_the_cookie_uses_dots_so_commas_are_not_quoted() -> None:
    assert encode_order(("create", "projects")) == (
        "create.projects.board.calendar.backlog.sprints.schedules"
    )
    assert parse_order("schedules.create.projects")[0] == "schedules"


def test_project_links_are_omitted_until_a_project_is_in_context() -> None:
    keys = [item.key for item in links_for(parse_order(None), None)]
    assert keys == ["projects", "create", "board", "calendar"]
    assert links_for(parse_order(None), None)[2].href == "/board"
    assert links_for(parse_order(None), None)[3].href == "/calendar"
    inside = [item.key for item in links_for(parse_order(None), "TEST")]
    assert inside == [
        "projects",
        "create",
        "board",
        "calendar",
        "backlog",
        "sprints",
        "schedules",
    ]
    assert links_for(parse_order(None), "TEST")[2].href.endswith("/projects/TEST/board")
    assert links_for(parse_order(None), "TEST")[3].href == "/projects/TEST/calendar"
