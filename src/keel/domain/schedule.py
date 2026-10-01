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
    start_offset_days: int | None,
    start_minute_of_day: int | None,
    due_offset_days: int | None,
    due_minute_of_day: int | None,
) -> None:
    _check_offset_side(
        start_offset_days,
        start_minute_of_day,
        "Start offset is how many days before the occurrence.",
    )
    _check_offset_side(
        due_offset_days,
        due_minute_of_day,
        "Due offset is how many days after the occurrence.",
    )
    if (
        start_offset_days is None
        or start_minute_of_day is None
        or due_offset_days is None
        or due_minute_of_day is None
    ):
        return
    start = -start_offset_days * MINUTES_PER_DAY + start_minute_of_day
    due = due_offset_days * MINUTES_PER_DAY + due_minute_of_day
    if start > due:
        raise InvalidSeriesError("Start cannot be after due.")


def _check_offset_side(
    offset_days: int | None,
    minute_of_day: int | None,
    negative_message: str,
) -> None:
    if offset_days is None and minute_of_day is None:
        return
    if offset_days is None or minute_of_day is None:
        raise InvalidSeriesError(
            "A start or due needs both a day offset and a time, or neither.",
        )
    if offset_days < 0:
        raise InvalidSeriesError(negative_message)
    check_minute_of_day(minute_of_day)


def complete_offset_pair(
    offset_days: int | None,
    minute_of_day: int | None,
) -> tuple[int | None, int | None]:
    """Fill one blank half of a set pair. Both blank stays unset."""
    if offset_days is None and minute_of_day is None:
        return None, None
    return (
        0 if offset_days is None else offset_days,
        0 if minute_of_day is None else minute_of_day,
    )


def occurrence_at(
    occurrence_on: date,
    offset_days: int,
    minute_of_day: int,
) -> datetime:
    check_minute_of_day(minute_of_day)
    day = occurrence_on + timedelta(days=offset_days)
    hours, minutes = divmod(minute_of_day, 60)
    return datetime(day.year, day.month, day.day, hours, minutes)


def recipe_start_at(
    occurrence_on: date,
    start_offset_days: int | None,
    start_minute_of_day: int | None,
) -> datetime | None:
    if start_offset_days is None or start_minute_of_day is None:
        return None
    return occurrence_at(occurrence_on, -start_offset_days, start_minute_of_day)


def recipe_due_at(
    occurrence_on: date,
    due_offset_days: int | None,
    due_minute_of_day: int | None,
) -> datetime | None:
    if due_offset_days is None or due_minute_of_day is None:
        return None
    return occurrence_at(occurrence_on, due_offset_days, due_minute_of_day)


def offsets_for_window(
    occurrence_on: date,
    start_at: datetime | None,
    due_at: datetime | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    start_offset_days: int | None
    start_minute_of_day: int | None
    due_offset_days: int | None
    due_minute_of_day: int | None
    if start_at is None:
        start_offset_days = None
        start_minute_of_day = None
    else:
        signed_start_days, start_minute_of_day = offsets_from(occurrence_on, start_at)
        start_offset_days = -signed_start_days
    if due_at is None:
        due_offset_days = None
        due_minute_of_day = None
    else:
        due_offset_days, due_minute_of_day = offsets_from(occurrence_on, due_at)
    check_recipe_window(
        start_offset_days,
        start_minute_of_day,
        due_offset_days,
        due_minute_of_day,
    )
    return (
        start_offset_days,
        start_minute_of_day,
        due_offset_days,
        due_minute_of_day,
    )


def offsets_from(occurrence_on: date, instant: datetime) -> tuple[int, int]:
    naive = _naive_utc(instant)
    offset_days = (naive.date() - occurrence_on).days
    minute_of_day = naive.hour * 60 + naive.minute
    return offset_days, minute_of_day


def recipe_offsets_from(
    occurrence_on: date,
    start_at: datetime,
    due_at: datetime,
) -> tuple[int, int, int, int]:
    signed_start_days, start_minute_of_day = offsets_from(occurrence_on, start_at)
    signed_due_days, due_minute_of_day = offsets_from(occurrence_on, due_at)
    start_offset_days = -signed_start_days
    due_offset_days = signed_due_days
    check_recipe_window(
        start_offset_days,
        start_minute_of_day,
        due_offset_days,
        due_minute_of_day,
    )
    return start_offset_days, start_minute_of_day, due_offset_days, due_minute_of_day


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
