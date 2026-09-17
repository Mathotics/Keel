from datetime import date, datetime

import pytest

from keel.domain.errors import InvalidIssueError, InvalidSeriesError
from keel.domain.schedule import (
    check_recipe_window,
    check_start_due_window,
    format_clock,
    occurrence_at,
    offsets_from,
    parse_clock,
)


def test_a_blank_side_of_the_window_is_allowed() -> None:
    start = datetime(2026, 9, 15, 9, 0)
    check_start_due_window(start, None)
    check_start_due_window(None, start)


def test_start_after_due_is_refused() -> None:
    with pytest.raises(InvalidIssueError, match="Start cannot be after due"):
        check_start_due_window(
            datetime(2026, 9, 16, 9, 0),
            datetime(2026, 9, 15, 17, 0),
        )


def test_equal_start_and_due_are_allowed() -> None:
    instant = datetime(2026, 9, 15, 17, 0)
    check_start_due_window(instant, instant)


def test_occurrence_offsets_round_trip() -> None:
    occurrence = date(2026, 9, 15)
    instant = occurrence_at(occurrence, -1, 9 * 60)
    assert instant == datetime(2026, 9, 14, 9, 0)
    assert offsets_from(occurrence, instant) == (-1, 9 * 60)


def test_recipe_window_refuses_start_after_due() -> None:
    with pytest.raises(InvalidSeriesError, match="Start cannot be after due"):
        check_recipe_window(0, 17 * 60, 0, 9 * 60)


def test_clock_parsing() -> None:
    assert parse_clock("") == 0
    assert parse_clock("09:30") == 9 * 60 + 30
    assert format_clock(9 * 60 + 30) == "09:30"
    with pytest.raises(InvalidSeriesError):
        parse_clock("24:00")
