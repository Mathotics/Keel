import pytest

from keel.domain.errors import InvalidCostError
from keel.domain.money import (
    estimate_at_completion,
    format_cents,
    format_ratio,
    parse_cost,
    performance_index,
)


def test_blank_cost_is_unset() -> None:
    assert parse_cost("  ") is None


def test_dollars_become_cents() -> None:
    assert parse_cost("12") == 1200
    assert parse_cost("12.5") == 1250
    assert parse_cost("12.50") == 1250
    assert parse_cost("$1,234.56") == 123456
    assert parse_cost("0") == 0


def test_a_malformed_cost_is_refused() -> None:
    for raw in ("-1", "12.345", "1,23", "$", "12.5.0", "free"):
        with pytest.raises(InvalidCostError) as caught:
            parse_cost(raw)
        assert caught.value.code == "issue.invalid_cost"


def test_cents_format_with_a_thousands_separator() -> None:
    assert format_cents(0) == "$0.00"
    assert format_cents(1250) == "$12.50"
    assert format_cents(123456) == "$1,234.56"
    assert format_cents(-50) == "-$0.50"


def test_a_ratio_keeps_two_places_and_drops_trailing_zeros() -> None:
    assert format_ratio(None) == ""
    assert format_ratio(0.0) == "0.00"
    assert format_ratio(1.5) == "1.50"
    assert format_ratio(1.25) == "1.25"
    assert format_ratio(0.3333) == "0.3333"


def test_an_index_is_undefined_when_the_divisor_is_missing_or_zero() -> None:
    assert performance_index(None, 100) is None
    assert performance_index(50, None) is None
    assert performance_index(50, 0) is None
    assert performance_index(1, 3) == 0.3333


def test_estimate_at_completion_needs_all_three_totals() -> None:
    assert estimate_at_completion(None, 0, 0) is None
    assert estimate_at_completion(1000, 400, 500) == 1100
