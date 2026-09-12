"""Pure calendar math for auto-sprint windows."""

from calendar import monthrange
from datetime import date, timedelta

from keel.domain.enums import SprintCadence
from keel.domain.errors import InvalidSprintCadenceError


def window_end(
    start: date,
    cadence: SprintCadence,
    n_days: int | None = None,
) -> date:
    """Inclusive last day of a window that starts on `start`."""
    if cadence is SprintCadence.WEEKLY:
        return start + timedelta(days=6)
    if cadence is SprintCadence.TWO_WEEKS:
        return start + timedelta(days=13)
    if cadence is SprintCadence.EVERY_N_DAYS:
        return start + timedelta(days=_positive_days(n_days) - 1)
    if cadence is SprintCadence.MONTHLY:
        return add_one_month(start)
    raise InvalidSprintCadenceError("Auto-sprint is off, so there is no window.")


def add_one_month(day: date) -> date:
    """Same day-of-month next month, clamped to that month's last day."""
    if day.month == 12:
        year, month = day.year + 1, 1
    else:
        year, month = day.year, day.month + 1
    last = monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def next_window_start(closed_end: date | None, today: date) -> date:
    """Day after a closed sprint's last day, or today when catching up or undated."""
    if closed_end is None or closed_end >= today:
        return today
    start = closed_end + timedelta(days=1)
    return today if start < today else start


def window_name(starts_on: date, ends_on: date) -> str:
    """Human date window, for example '12 Sep – 26 Sep 2026'."""
    left = f"{starts_on.day} {starts_on.strftime('%b')}"
    right = f"{ends_on.day} {ends_on.strftime('%b %Y')}"
    if starts_on.year != ends_on.year:
        left = f"{starts_on.day} {starts_on.strftime('%b %Y')}"
    return f"{left} – {right}"


def _positive_days(n_days: int | None) -> int:
    if n_days is None or n_days < 1:
        raise InvalidSprintCadenceError(
            "Every N days needs a number of days of at least 1.",
        )
    return n_days
