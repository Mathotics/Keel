"""Money as whole cents, and the earned-value ratios derived from it."""

import re
from decimal import ROUND_HALF_UP, Decimal

from keel.domain.currency import (
    DEFAULT_CURRENCY,
    SYMBOLS,
    display_places,
)
from keel.domain.errors import InvalidCostError

_MAX_CENTS = 9_007_199_254_740_991
_NUMBER = re.compile(r"^(?:(\d{1,3}(?:,\d{3})*)|(\d+))(?:\.(\d{1,2}))?$")
_SYMBOLS_LONGEST_FIRST = tuple(sorted(set(SYMBOLS.values()), key=len, reverse=True))


def cost_example(currency: str = DEFAULT_CURRENCY) -> str:
    """An example amount in this project's currency."""
    symbol = SYMBOLS.get(currency, "")
    return f"12, 12.50, or {symbol}1,234.56 {currency}"


def parse_cost(raw: str, currency: str = DEFAULT_CURRENCY) -> int | None:
    """Read an amount as cents. Blank means unset.

    A bare number is accepted, as is the formatted field value. A symbol or
    code for a different currency is refused. At most two decimal places.
    """
    code = (currency or DEFAULT_CURRENCY).strip().upper()
    cleaned = raw.strip()
    if not cleaned:
        return None
    example = cost_example(code)
    if "-" in cleaned:
        raise InvalidCostError(f"Cost must look like {example}.", value=raw)
    body, refused = _without_code(cleaned, code)
    if refused or body is None:
        raise InvalidCostError(f"Cost must look like {example}.", value=raw)
    number, refused = _without_symbol(body, code)
    if refused or number is None:
        raise InvalidCostError(f"Cost must look like {example}.", value=raw)
    matched = _NUMBER.fullmatch(number)
    if matched is None:
        raise InvalidCostError(f"Cost must look like {example}.", value=raw)
    dollars_text = (matched.group(1) or matched.group(2)).replace(",", "")
    fraction = (matched.group(3) or "").ljust(2, "0")
    cents = int(dollars_text) * 100 + int(fraction or "0")
    if cents > _MAX_CENTS:
        raise InvalidCostError(f"Cost must look like {example}.", value=raw)
    return cents


def format_money_edit(cents: int, currency: str = DEFAULT_CURRENCY) -> str:
    """The edit-field value: two decimal places, symbol, and code."""
    return _format(cents, currency, places=2)


def format_money_display(cents: int, currency: str = DEFAULT_CURRENCY) -> str:
    """A read-only amount in the currency's usual decimal places."""
    return _format(cents, currency, places=display_places(currency))


def format_cents(cents: int) -> str:
    """USD edit form, kept for callers that still mean dollars."""
    return format_money_edit(cents, DEFAULT_CURRENCY)


def _format(cents: int, currency: str, *, places: int) -> str:
    code = (currency or DEFAULT_CURRENCY).strip().upper()
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    if places == 0:
        body = f"{absolute // 100:,}"
    else:
        major, remainder = divmod(absolute, 100)
        body = f"{major:,}.{remainder:02d}"
    symbol = SYMBOLS.get(code, "")
    return f"{sign}{symbol}{body} {code}"


def _without_code(text: str, code: str) -> tuple[str | None, bool]:
    if len(text) >= 3 and text[-3:].isalpha():
        suffix = text[-3:].upper()
        if suffix != code:
            return None, True
        return text[:-3].strip(), False
    return text, False


def _without_symbol(text: str, code: str) -> tuple[str | None, bool]:
    symbol = SYMBOLS.get(code, "")
    for known in _SYMBOLS_LONGEST_FIRST:
        if text.startswith(known):
            if known != symbol:
                return None, True
            return text[len(known) :].strip(), False
    return text, False


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
