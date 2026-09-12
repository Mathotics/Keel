from datetime import date

import pytest

from keel.domain.cadence import (
    add_one_month,
    next_window_start,
    window_end,
    window_name,
)
from keel.domain.enums import SprintCadence
from keel.domain.errors import InvalidSprintCadenceError


def test_weekly_is_seven_inclusive_days() -> None:
    assert window_end(date(2026, 9, 12), SprintCadence.WEEKLY) == date(2026, 9, 18)


def test_two_weeks_is_fourteen_inclusive_days() -> None:
    assert window_end(date(2026, 9, 12), SprintCadence.TWO_WEEKS) == date(2026, 9, 25)


def test_n_days_is_inclusive() -> None:
    assert window_end(date(2026, 9, 12), SprintCadence.EVERY_N_DAYS, 1) == date(
        2026,
        9,
        12,
    )
    assert window_end(date(2026, 9, 12), SprintCadence.EVERY_N_DAYS, 10) == date(
        2026,
        9,
        21,
    )


def test_n_days_refuses_a_missing_or_non_positive_count() -> None:
    with pytest.raises(InvalidSprintCadenceError) as caught:
        window_end(date(2026, 9, 12), SprintCadence.EVERY_N_DAYS, None)
    assert caught.value.code == "project.invalid_cadence"


def test_monthly_uses_the_same_day_next_month() -> None:
    assert window_end(date(2026, 9, 12), SprintCadence.MONTHLY) == date(2026, 10, 12)


def test_monthly_clamps_to_the_last_day_of_the_month() -> None:
    assert add_one_month(date(2026, 1, 31)) == date(2026, 2, 28)
    assert add_one_month(date(2024, 1, 31)) == date(2024, 2, 29)
    assert add_one_month(date(2026, 12, 15)) == date(2027, 1, 15)


def test_off_has_no_window() -> None:
    with pytest.raises(InvalidSprintCadenceError):
        window_end(date(2026, 9, 12), SprintCadence.OFF)


def test_a_timely_next_window_starts_the_day_after_the_close() -> None:
    assert next_window_start(date(2026, 9, 18), date(2026, 9, 19)) == date(2026, 9, 19)


def test_catch_up_starts_today_rather_than_backfilling() -> None:
    assert next_window_start(date(2026, 9, 1), date(2026, 9, 19)) == date(2026, 9, 19)


def test_an_early_complete_starts_today() -> None:
    assert next_window_start(date(2026, 9, 18), date(2026, 9, 12)) == date(2026, 9, 12)


def test_window_names_put_the_year_on_the_end() -> None:
    assert window_name(date(2026, 9, 12), date(2026, 9, 26)) == "12 Sep – 26 Sep 2026"


def test_window_names_keep_both_years_when_they_differ() -> None:
    assert (
        window_name(date(2026, 12, 26), date(2027, 1, 8)) == "26 Dec 2026 – 8 Jan 2027"
    )
