from keel.web.paging import DEFAULT_ISSUE_PAGE_SIZE, ISSUE_PAGE_SIZES, issue_page


def test_the_menu_is_the_sizes_the_project_page_offers() -> None:
    assert ISSUE_PAGE_SIZES == (1, 5, 10, 20, 50, 100)
    assert DEFAULT_ISSUE_PAGE_SIZE == 20


def test_a_page_is_a_slice_of_the_list() -> None:
    window = issue_page(12, page=2, size=5)

    assert window.page == 2
    assert window.page_size == 5
    assert window.pages == 3
    assert window.offset == 5
    assert (window.start, window.end) == (6, 10)
    assert window.has_previous is True
    assert window.has_next is True


def test_the_last_page_stops_at_the_last_issue() -> None:
    window = issue_page(12, page=3, size=5)

    assert window.offset == 10
    assert (window.start, window.end) == (11, 12)
    assert window.has_previous is True
    assert window.has_next is False


def test_a_page_past_the_end_lands_on_the_last_page() -> None:
    window = issue_page(12, page=99, size=5)

    assert window.page == 3
    assert window.has_next is False


def test_a_page_before_the_first_lands_on_the_first_page() -> None:
    window = issue_page(12, page=0, size=5)

    assert window.page == 1
    assert window.offset == 0
    assert window.has_previous is False


def test_an_unknown_size_uses_the_default() -> None:
    window = issue_page(21, page=1, size=7)

    assert window.page_size == DEFAULT_ISSUE_PAGE_SIZE
    assert window.pages == 2
    assert (window.start, window.end) == (1, 20)


def test_an_empty_project_is_one_blank_page() -> None:
    window = issue_page(0, page=4, size=10)

    assert window.page == 1
    assert window.pages == 1
    assert window.offset == 0
    assert (window.start, window.end, window.total) == (0, 0, 0)
    assert window.has_previous is False
    assert window.has_next is False
