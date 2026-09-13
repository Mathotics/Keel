from datetime import date

import pytest

from keel.domain.enums import RecurrenceFreq
from keel.domain.errors import InvalidSeriesError
from keel.domain.recurrence import (
    Recurrence,
    next_on_or_after,
    occurrence_dates,
    parse_weekdays,
)


def test_daily_occurrences_stop_on_the_until_date() -> None:
    rec = Recurrence(
        freq=RecurrenceFreq.DAILY,
        starts_on=date(2026, 9, 12),
        ends_on=date(2026, 9, 14),
    )
    assert occurrence_dates(rec, date(2026, 10, 1)) == [
        date(2026, 9, 12),
        date(2026, 9, 13),
        date(2026, 9, 14),
    ]


def test_weekly_on_chosen_weekdays_uses_the_interval() -> None:
    rec = Recurrence(
        freq=RecurrenceFreq.WEEKLY,
        starts_on=date(2026, 9, 7),
        interval=2,
        weekdays=(0,),
        count=3,
    )
    assert occurrence_dates(rec, date(2026, 12, 1)) == [
        date(2026, 9, 7),
        date(2026, 9, 21),
        date(2026, 10, 5),
    ]


def test_monthly_nth_weekday_and_from_now_skips_the_past() -> None:
    rec = Recurrence(
        freq=RecurrenceFreq.MONTHLY,
        starts_on=date(2026, 9, 8),
        weekdays=(1,),
        nth_week=2,
    )
    assert next_on_or_after(rec, date(2026, 10, 1)) == date(2026, 10, 13)


def test_monthly_on_a_day_and_yearly_summaries() -> None:
    monthly = Recurrence(
        freq=RecurrenceFreq.MONTHLY,
        starts_on=date(2026, 1, 31),
        month_day=31,
        interval=2,
        count=3,
    )
    assert occurrence_dates(monthly, date(2026, 8, 1)) == [
        date(2026, 1, 31),
        date(2026, 3, 31),
        date(2026, 5, 31),
    ]
    assert monthly.summary() == "Every 2 months on day 31, 3 times"
    yearly = Recurrence(
        freq=RecurrenceFreq.YEARLY,
        starts_on=date(2026, 2, 1),
        month=2,
        month_day=1,
        interval=1,
        ends_on=date(2028, 2, 1),
    )
    assert occurrence_dates(yearly, date(2030, 1, 1)) == [
        date(2026, 2, 1),
        date(2027, 2, 1),
        date(2028, 2, 1),
    ]
    assert yearly.summary() == "Yearly on 1 Feb until 2028-02-01"
    last = Recurrence(
        freq=RecurrenceFreq.MONTHLY,
        starts_on=date(2026, 9, 1),
        weekdays=(0,),
        nth_week=-1,
        interval=1,
    )
    assert last.summary() == "Monthly on the last Mon"


def test_invalid_recurrence_and_weekdays_are_refused() -> None:
    with pytest.raises(InvalidSeriesError):
        occurrence_dates(
            Recurrence(
                freq=RecurrenceFreq.DAILY,
                starts_on=date(2026, 9, 12),
                interval=0,
            ),
            date(2026, 9, 12),
        )
    with pytest.raises(InvalidSeriesError):
        parse_weekdays("9")
    with pytest.raises(InvalidSeriesError):
        parse_weekdays("x")
    assert parse_weekdays("") == ()
    assert parse_weekdays("0,2,0") == (0, 2)
