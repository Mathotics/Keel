"""One page control for every table that should not render every row."""

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlencode

PAGE_SIZES = (1, 5, 10, 20, 50, 100)
DEFAULT_PAGE_SIZE = 20


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


@dataclass(frozen=True)
class PagerRequest:
    """What one table asks the shared pager to show.

    ``key`` prefixes the query (``planned`` becomes ``planned_page``). An
    empty key uses ``page`` and ``size``, for a page with a single table.
    ``keep`` is extra query fields, such as filters, that stay on every
    link and in the size form.
    """

    label: str
    field_id: str
    aria_label: str
    empty: str
    total: int
    page: int
    size: int
    key: str = ""
    keep: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TablePager:
    """Everything the shared pager template needs to render one table."""

    label: str
    field_id: str
    aria_label: str
    empty: str
    action: str
    size_name: str
    window: PageWindow
    sizes: tuple[int, ...]
    hidden: tuple[tuple[str, int | str], ...]
    first_href: str
    previous_href: str
    next_href: str
    last_href: str


def page_window(total: int, page: int, size: int) -> PageWindow:
    """Clamp a requested page onto the allowed sizes.

    A size outside the menu falls back to the default. A page before the
    first, or past the last, lands on the nearest real page. An empty list
    is still one page so the controls stay in place.
    """
    page_size = size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE
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


def page_rows[Row](rows: Sequence[Row], window: PageWindow) -> Sequence[Row]:
    """The rows that belong on this page. The input order is kept."""
    return rows[window.offset : window.offset + window.page_size]


def table_pagers(path: str, requests: Sequence[PagerRequest]) -> list[TablePager]:
    """Build one pager per table on ``path``.

    Turning a page, or changing a size, rewrites only that table's query
    fields. The other tables on the same path stay where they are.
    """
    windows = [page_window(item.total, item.page, item.size) for item in requests]
    pagers: list[TablePager] = []
    for index, item in enumerate(requests):
        window = windows[index]
        page_name, size_name = _names(item.key)
        hidden: list[tuple[str, int | str]] = [(page_name, 1)]
        for other_index, other in enumerate(requests):
            if other_index == index:
                continue
            other_page, other_size = _names(other.key)
            hidden.append((other_page, windows[other_index].page))
            hidden.append((other_size, windows[other_index].page_size))
        hidden.extend(_kept(item.keep))
        pagers.append(
            TablePager(
                label=item.label,
                field_id=item.field_id,
                aria_label=item.aria_label,
                empty=item.empty,
                action=path,
                size_name=size_name,
                window=window,
                sizes=PAGE_SIZES,
                hidden=tuple(hidden),
                first_href=_href(path, requests, windows, index, 1),
                previous_href=_href(
                    path,
                    requests,
                    windows,
                    index,
                    max(window.page - 1, 1),
                ),
                next_href=_href(path, requests, windows, index, window.page + 1),
                last_href=_href(path, requests, windows, index, window.pages),
            )
        )
    return pagers


def one_pager(path: str, request: PagerRequest) -> TablePager:
    """The pager for a page that has a single table."""
    return table_pagers(path, (request,))[0]


def _names(key: str) -> tuple[str, str]:
    if key:
        return f"{key}_page", f"{key}_size"
    return "page", "size"


def _href(
    path: str,
    requests: Sequence[PagerRequest],
    windows: Sequence[PageWindow],
    focus: int,
    page: int,
) -> str:
    pairs: list[tuple[str, int | str]] = []
    for index, item in enumerate(requests):
        page_name, size_name = _names(item.key)
        shown = page if index == focus else windows[index].page
        pairs.append((page_name, shown))
        pairs.append((size_name, windows[index].page_size))
    pairs.extend(_kept(requests[focus].keep))
    return f"{path}?{urlencode(pairs)}"


def _kept(pairs: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    return tuple((name, value) for name, value in pairs if value != "")
