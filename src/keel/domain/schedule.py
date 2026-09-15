"""Start/due windows and series occurrence offsets."""

from datetime import UTC, date, datetime, timedelta

from keel.domain.errors import InvalidIssueError, InvalidSeriesError

MINUTES_PER_DAY = 24 * 60


def check_start_due_window(
    start_at: datetime | None,
    due_at: datetime | None,
) -> None:
    if start_at is None or due_at is None:
        return
    if _naive_utc(start_at) > _naive_utc(due_at):
        raise InvalidIssueError("Start cannot be after due.")


def check_minute_of_day(value: int) -> None:
    if value < 0 or value >= MINUTES_PER_DAY:
        raise InvalidSeriesError("Clock time must be on the clock.")


def check_recipe_window(
    start_offset_days: int,
    start_minute_of_day: int,
    due_offset_days: int,
    due_minute_of_day: int,
) -> None:
    check_minute_of_day(start_minute_of_day)
    check_minute_of_day(due_minute_of_day)
    start = start_offset_days * MINUTES_PER_DAY + start_minute_of_day
    due = due_offset_days * MINUTES_PER_DAY + due_minute_of_day
    if start > due:
        raise InvalidSeriesError("Start cannot be after due.")


def occurrence_at(
    occurrence_on: date,
    offset_days: int,
    minute_of_day: int,
) -> datetime:
    check_minute_of_day(minute_of_day)
    day = occurrence_on + timedelta(days=offset_days)
    hours, minutes = divmod(minute_of_day, 60)
    return datetime(day.year, day.month, day.day, hours, minutes)


def offsets_from(occurrence_on: date, instant: datetime) -> tuple[int, int]:
    naive = _naive_utc(instant)
    offset_days = (naive.date() - occurrence_on).days
    minute_of_day = naive.hour * 60 + naive.minute
    return offset_days, minute_of_day


def format_clock(minute_of_day: int) -> str:
    check_minute_of_day(minute_of_day)
    hours, minutes = divmod(minute_of_day, 60)
    return f"{hours:02d}:{minutes:02d}"


def parse_clock(raw: str) -> int:
    cleaned = raw.strip()
    if not cleaned:
        return 0
    parts = cleaned.split(":")
    try:
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
    except ValueError as exc:
        raise InvalidSeriesError("Clock time could not be read.") from exc
    value = hours * 60 + minutes
    check_minute_of_day(value)
    return value


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
