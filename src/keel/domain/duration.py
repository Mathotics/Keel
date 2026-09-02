import re

from keel.domain.errors import InvalidDurationError

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 8
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY

_TOKEN = re.compile(r"^(\d+)([dhm])$", re.IGNORECASE)
_EXAMPLE = "2h, 90m, 1h 30m, or 1d"


def parse_duration(raw: str) -> int | None:
    """Read shorthand effort. Blank means unset; anything else must be exact."""
    cleaned = " ".join(raw.strip().split())
    if not cleaned:
        return None
    seen: set[str] = set()
    total = 0
    for part in cleaned.split(" "):
        matched = _TOKEN.fullmatch(part)
        if matched is None:
            raise InvalidDurationError(
                f"Effort must look like {_EXAMPLE}.",
                value=raw,
            )
        amount, unit = int(matched.group(1)), matched.group(2).lower()
        if unit in seen:
            raise InvalidDurationError(
                f"Effort must look like {_EXAMPLE}.",
                value=raw,
            )
        seen.add(unit)
        if unit == "d":
            total += amount * MINUTES_PER_DAY
        elif unit == "h":
            total += amount * MINUTES_PER_HOUR
        else:
            total += amount
    return total


def format_minutes(minutes: int) -> str:
    """Canonical shorthand: days (eight hours), then hours, then minutes."""
    days, rest = divmod(minutes, MINUTES_PER_DAY)
    hours, remaining = divmod(rest, MINUTES_PER_HOUR)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if remaining or not parts:
        parts.append(f"{remaining}m")
    return " ".join(parts)
