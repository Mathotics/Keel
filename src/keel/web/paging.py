"""Fixed-size windows for lists that should not render every row."""

from dataclasses import dataclass

ISSUE_PAGE_SIZES = (1, 5, 10, 20, 50, 100)
DEFAULT_ISSUE_PAGE_SIZE = 20


@dataclass(frozen=True)
class PageWindow:
    """One slice of a list, with the controls needed to move off it."""

    page: int
    page_size: int
    total: int
    pages: int
    offset: int
    start: int
    end: int

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


def issue_page(total: int, page: int, size: int) -> PageWindow:
    """Clamp a requested page onto the allowed sizes.

    A size outside the menu falls back to the default. A page before the
    first, or past the last, lands on the nearest real page. An empty list
    is still one page so the controls stay in place.
    """
    page_size = size if size in ISSUE_PAGE_SIZES else DEFAULT_ISSUE_PAGE_SIZE
    pages = (total + page_size - 1) // page_size if total else 1
    current = min(max(page, 1), pages)
    offset = (current - 1) * page_size
    if total:
        start = offset + 1
        end = min(offset + page_size, total)
    else:
        start = 0
        end = 0
    return PageWindow(
        page=current,
        page_size=page_size,
        total=total,
        pages=pages,
        offset=offset,
        start=start,
        end=end,
    )
