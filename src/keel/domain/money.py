"""Money as whole cents, and the earned-value ratios derived from it."""

import re
from decimal import ROUND_HALF_UP, Decimal

from keel.domain.errors import InvalidCostError

_MAX_CENTS = 9_007_199_254_740_991
_EXAMPLE = "12, 12.50, or $1,234.56"
_MONEY = re.compile(r"^\$?(?:(\d{1,3}(?:,\d{3})*)|(\d+))(?:\.(\d{1,2}))?$")


def parse_cost(raw: str) -> int | None:
    """Read a dollar amount as cents. Blank means unset."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.startswith("-"):
        raise InvalidCostError(f"Cost must look like {_EXAMPLE}.", value=raw)
    matched = _MONEY.fullmatch(cleaned)
    if matched is None:
        raise InvalidCostError(f"Cost must look like {_EXAMPLE}.", value=raw)
    dollars_text = (matched.group(1) or matched.group(2)).replace(",", "")
    fraction = (matched.group(3) or "").ljust(2, "0")
    cents = int(dollars_text) * 100 + int(fraction or "0")
    if cents > _MAX_CENTS:
        raise InvalidCostError(f"Cost must look like {_EXAMPLE}.", value=raw)
    return cents


def format_cents(cents: int) -> str:
    """Canonical dollars, with a thousands separator and two decimal places."""
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{remainder:02d}"


def format_ratio(value: float | None) -> str:
    """A performance index for display. Unset stays blank."""
    if value is None:
        return ""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".00"
    elif len(text.split(".")[1]) < 2:
        text += "0"
    return text


def performance_index(numerator: int | None, denominator: int | None) -> float | None:
    """Ratio rounded half up to four places. A missing or zero divisor is undefined."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    ratio = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
    return float(ratio)


def estimate_at_completion(
    planned: int | None,
    earned: int | None,
    actual: int | None,
) -> int | None:
    """AC + (BAC − EV). Past spend stays; remaining budgeted work is priced at plan.

    Null unless planned, earned, and actual are all present. BAC is the planned total.
    """
    if planned is None or earned is None or actual is None:
        return None
    return actual + planned - earned
