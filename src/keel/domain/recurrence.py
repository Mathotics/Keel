"""Outlook-style recurrence: daily, weekly, monthly, yearly, with interval."""

from calendar import monthrange
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from keel.domain.enums import RecurrenceFreq
from keel.domain.errors import InvalidSeriesError

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MAX_GENERATED = 400


@dataclass(frozen=True)
class Recurrence:
    freq: RecurrenceFreq
    starts_on: date
    interval: int = 1
    weekdays: tuple[int, ...] = ()
    month_day: int | None = None
    nth_week: int | None = None
    month: int | None = None
    ends_on: date | None = None
    count: int | None = None

    def summary(self) -> str:
        interval = self.interval
        if self.freq is RecurrenceFreq.DAILY:
            base = "Daily" if interval == 1 else f"Every {interval} days"
        elif self.freq is RecurrenceFreq.WEEKLY:
            days = self.weekdays or (self.starts_on.weekday(),)
            names = ", ".join(WEEKDAY_NAMES[day] for day in days)
            base = (
                f"Weekly on {names}"
                if interval == 1
                else f"Every {interval} weeks on {names}"
            )
        elif self.freq is RecurrenceFreq.MONTHLY:
            if self.nth_week is not None:
                day = (self.weekdays or (self.starts_on.weekday(),))[0]
                rank = "last" if self.nth_week < 0 else _ordinal(self.nth_week)
                unit = (
                    f"the {rank} {WEEKDAY_NAMES[day]}"
                    if interval == 1
                    else f"every {interval} months on the {rank} {WEEKDAY_NAMES[day]}"
                )
                base = unit if interval > 1 else f"Monthly on {unit}"
            else:
                day = self.month_day or self.starts_on.day
                base = (
                    f"Monthly on day {day}"
                    if interval == 1
                    else f"Every {interval} months on day {day}"
                )
        else:
            month = self.month or self.starts_on.month
            day = self.month_day or self.starts_on.day
            stamp = date(2000, month, min(day, 28)).strftime("%d %b").lstrip("0")
            base = (
                f"Yearly on {stamp}"
                if interval == 1
                else f"Every {interval} years on {stamp}"
            )
        if self.ends_on is not None:
            return f"{base} until {self.ends_on.isoformat()}"
        if self.count is not None:
            return f"{base}, {self.count} times"
        return base


def parse_weekdays(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        return ()
    try:
        days = tuple(int(part) for part in raw.split(",") if part.strip() != "")
    except ValueError as exc:
        raise InvalidSeriesError("Weekdays could not be read.") from exc
    if any(day < 0 or day > 6 for day in days):
        raise InvalidSeriesError("Weekdays must be Monday=0 through Sunday=6.")
    return tuple(sorted(set(days)))


def encode_weekdays(days: tuple[int, ...]) -> str:
    return ",".join(str(day) for day in days)


def occurrence_dates(recurrence: Recurrence, until: date) -> list[date]:
    return list(_iter_occurrences(recurrence, until))


def next_on_or_after(
    recurrence: Recurrence,
    day: date,
    *,
    skip: set[date] | None = None,
    existing: set[date] | None = None,
) -> date | None:
    blocked = (skip or set()) | (existing or set())
    horizon = max(day, recurrence.starts_on) + timedelta(days=366 * 2)
    for occ in _iter_occurrences(recurrence, horizon):
        if occ < day or occ in blocked:
            continue
        return occ
    return None


def _iter_occurrences(recurrence: Recurrence, until: date) -> Iterator[date]:
    _validate(recurrence)
    produced = 0
    for occ in _raw_dates(recurrence, until):
        if occ < recurrence.starts_on:
            continue
        if recurrence.ends_on is not None and occ > recurrence.ends_on:
            break
        if occ > until:
            break
        yield occ
        produced += 1
        if recurrence.count is not None and produced >= recurrence.count:
            break
        if produced >= MAX_GENERATED:
            break


def _raw_dates(recurrence: Recurrence, until: date) -> Iterator[date]:
    if recurrence.freq is RecurrenceFreq.DAILY:
        current = recurrence.starts_on
        while current <= until:
            yield current
            current += timedelta(days=recurrence.interval)
        return
    if recurrence.freq is RecurrenceFreq.WEEKLY:
        days = recurrence.weekdays or (recurrence.starts_on.weekday(),)
        week_start = recurrence.starts_on - timedelta(
            days=recurrence.starts_on.weekday(),
        )
        week = 0
        while True:
            origin = week_start + timedelta(weeks=week * recurrence.interval)
            if origin > until + timedelta(days=7):
                return
            for weekday in days:
                occ = origin + timedelta(days=weekday)
                if occ > until and occ > recurrence.starts_on + timedelta(days=7):
                    return
                yield occ
            week += 1
        return
    if recurrence.freq is RecurrenceFreq.MONTHLY:
        year, month = recurrence.starts_on.year, recurrence.starts_on.month
        while date(year, month, 1) <= until:
            monthly = _monthly_date(recurrence, year, month)
            if monthly is not None:
                yield monthly
            year, month = _add_months(year, month, recurrence.interval)
        return
    year = recurrence.starts_on.year
    while year <= until.year + 1:
        yearly = _yearly_date(recurrence, year)
        if yearly is not None:
            yield yearly
        year += recurrence.interval


def _monthly_date(recurrence: Recurrence, year: int, month: int) -> date | None:
    if recurrence.nth_week is not None:
        weekday = (recurrence.weekdays or (recurrence.starts_on.weekday(),))[0]
        return _nth_weekday(year, month, weekday, recurrence.nth_week)
    day = recurrence.month_day or recurrence.starts_on.day
    last = monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _yearly_date(recurrence: Recurrence, year: int) -> date | None:
    month = recurrence.month or recurrence.starts_on.month
    if recurrence.nth_week is not None:
        weekday = (recurrence.weekdays or (recurrence.starts_on.weekday(),))[0]
        return _nth_weekday(year, month, weekday, recurrence.nth_week)
    day = recurrence.month_day or recurrence.starts_on.day
    last = monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date | None:
    if nth > 0:
        cursor = date(year, month, 1)
        while cursor.weekday() != weekday:
            cursor += timedelta(days=1)
        cursor += timedelta(weeks=nth - 1)
        if cursor.month != month:
            return None
        return cursor
    cursor = date(year, month, monthrange(year, month)[1])
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def _add_months(year: int, month: int, count: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + count
    return total // 12, total % 12 + 1


def _ordinal(value: int) -> str:
    if value == 1:
        return "1st"
    if value == 2:
        return "2nd"
    if value == 3:
        return "3rd"
    return f"{value}th"


def _validate(recurrence: Recurrence) -> None:
    if recurrence.interval < 1:
        raise InvalidSeriesError("Repeat interval must be at least 1.")
    if recurrence.count is not None and recurrence.count < 1:
        raise InvalidSeriesError("Occurrence count must be at least 1.")
    if recurrence.ends_on is not None and recurrence.ends_on < recurrence.starts_on:
        raise InvalidSeriesError("A series cannot end before it starts.")
    if recurrence.month_day is not None and not 1 <= recurrence.month_day <= 31:
        raise InvalidSeriesError("Month day must be between 1 and 31.")
    if recurrence.nth_week is not None and recurrence.nth_week not in {1, 2, 3, 4, -1}:
        raise InvalidSeriesError("Choose the 1st–4th or last weekday.")
    if recurrence.month is not None and not 1 <= recurrence.month <= 12:
        raise InvalidSeriesError("Month must be between 1 and 12.")
