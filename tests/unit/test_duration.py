import pytest

from keel.domain.duration import format_minutes, parse_duration
from keel.domain.errors import InvalidDurationError


@pytest.mark.parametrize(
    ("raw", "minutes"),
    [
        ("", None),
        ("  ", None),
        ("2h", 120),
        ("90m", 90),
        ("1h 30m", 90),
        ("1d", 480),
        ("1d 2h 30m", 630),
        ("2H", 120),
        ("  1h   30m  ", 90),
        ("30m 1h", 90),
        ("0m", 0),
        ("0h", 0),
    ],
)
def test_accepted_shorthand_parses_to_minutes(raw: str, minutes: int | None) -> None:
    assert parse_duration(raw) == minutes


@pytest.mark.parametrize(
    "raw",
    ["1h30", "1h30m", "1.5h", "1h 1h", "2x", "1 hour", "-2h", "h2", "1d2h"],
)
def test_unknown_shorthand_is_refused(raw: str) -> None:
    with pytest.raises(InvalidDurationError) as caught:
        parse_duration(raw)
    assert caught.value.code == "issue.invalid_duration"


@pytest.mark.parametrize(
    ("minutes", "shown"),
    [
        (0, "0m"),
        (45, "45m"),
        (60, "1h"),
        (90, "1h 30m"),
        (120, "2h"),
        (480, "1d"),
        (510, "1d 30m"),
        (630, "1d 2h 30m"),
    ],
)
def test_minutes_format_as_canonical_shorthand(minutes: int, shown: str) -> None:
    assert format_minutes(minutes) == shown


def test_formatting_round_trips_through_parsing() -> None:
    for minutes in (0, 1, 59, 60, 61, 90, 479, 480, 481, 1000):
        assert parse_duration(format_minutes(minutes)) == minutes
