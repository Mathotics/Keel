from keel.web.paging import (
    DEFAULT_PAGE_SIZE,
    PAGE_SIZES,
    PagerRequest,
    one_pager,
    page_rows,
    page_window,
    table_pagers,
)


def test_the_menu_is_the_sizes_every_table_offers() -> None:
    assert PAGE_SIZES == (1, 5, 10, 20, 50, 100)
    assert DEFAULT_PAGE_SIZE == 20


def test_a_page_is_a_slice_of_the_list() -> None:
    window = page_window(12, page=2, size=5)

    assert window.page == 2
    assert window.page_size == 5
    assert window.pages == 3
    assert window.offset == 5
    assert (window.start, window.end) == (6, 10)
    assert window.has_previous is True
    assert window.has_next is True
    assert page_rows(list("abcdefghijkl"), window) == list("fghij")


def test_the_last_page_stops_at_the_last_row() -> None:
    window = page_window(12, page=3, size=5)

    assert window.offset == 10
    assert (window.start, window.end) == (11, 12)
    assert window.has_previous is True
    assert window.has_next is False


def test_a_page_past_the_end_lands_on_the_last_page() -> None:
    window = page_window(12, page=99, size=5)

    assert window.page == 3
    assert window.has_next is False


def test_a_page_before_the_first_lands_on_the_first_page() -> None:
    window = page_window(12, page=0, size=5)

    assert window.page == 1
    assert window.offset == 0
    assert window.has_previous is False


def test_an_unknown_size_uses_the_default() -> None:
    window = page_window(21, page=1, size=7)

    assert window.page_size == DEFAULT_PAGE_SIZE
    assert window.pages == 2
    assert (window.start, window.end) == (1, 20)


def test_an_empty_list_is_one_blank_page() -> None:
    window = page_window(0, page=4, size=10)

    assert window.page == 1
    assert window.pages == 1
    assert window.offset == 0
    assert (window.start, window.end, window.total) == (0, 0, 0)
    assert window.has_previous is False
    assert window.has_next is False
    assert page_rows([], window) == []


def test_one_table_links_its_own_page_and_size() -> None:
    pager = one_pager(
        "/projects",
        PagerRequest(
            label="Projects per page",
            field_id="project-list-size",
            aria_label="Project pages",
            empty="0 projects",
            total=7,
            page=1,
            size=5,
        ),
    )

    assert pager.next_href == "/projects?page=2&size=5"
    assert pager.last_href == "/projects?page=2&size=5"
    assert pager.hidden == (("page", 1),)
    assert pager.size_name == "size"
    assert pager.sizes == PAGE_SIZES


def test_turning_one_table_leaves_the_other_tables_alone() -> None:
    planned, active, completed = table_pagers(
        "/projects/KEEL/sprints",
        (
            PagerRequest(
                label="Sprints per page",
                field_id="sprint-size-planned",
                aria_label="Planned pages",
                empty="0 sprints",
                total=7,
                page=2,
                size=5,
                key="planned",
            ),
            PagerRequest(
                label="Sprints per page",
                field_id="sprint-size-active",
                aria_label="Active pages",
                empty="0 sprints",
                total=0,
                page=1,
                size=20,
                key="active",
            ),
            PagerRequest(
                label="Sprints per page",
                field_id="sprint-size-completed",
                aria_label="Completed pages",
                empty="0 sprints",
                total=3,
                page=1,
                size=1,
                key="completed",
            ),
        ),
    )

    assert "planned_page=1" in planned.first_href
    assert "planned_size=5" in planned.first_href
    assert "active_page=1" in planned.first_href
    assert "active_size=20" in planned.first_href
    assert "completed_page=1" in planned.first_href
    assert "completed_size=1" in planned.first_href
    assert completed.next_href.endswith(
        "planned_page=2&planned_size=5&active_page=1&active_size=20"
        "&completed_page=2&completed_size=1"
    )
    assert planned.hidden == (
        ("planned_page", 1),
        ("active_page", 1),
        ("active_size", 20),
        ("completed_page", 1),
        ("completed_size", 1),
    )
    assert active.window.total == 0
    assert active.empty == "0 sprints"
