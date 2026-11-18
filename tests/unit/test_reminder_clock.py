import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from keel.domain.errors import InvalidReminderError
from keel.domain.reminders import (
    MAX_OVERDUE,
    Offset,
    Overdue,
    Rule,
    fire_dict,
    normalize_offsets,
    normalize_rule,
    plan_fires,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "reminder_clock.json"


def _when(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _rule(raw: dict[str, Any]) -> Rule:
    overdue = raw.get("overdue")
    return Rule(
        start_offsets=tuple(
            Offset(item["amount"], item["unit"])
            for item in raw.get("start_offsets", [])
        ),
        at_start=bool(raw.get("at_start")),
        due_offsets=tuple(
            Offset(item["amount"], item["unit"]) for item in raw.get("due_offsets", [])
        ),
        at_due=bool(raw.get("at_due")),
        overdue=None
        if overdue is None
        else Overdue(
            kind=overdue["kind"],
            amount=int(overdue.get("amount") or 1),
            unit=str(overdue.get("unit") or "minute"),
            minute_of_day=overdue.get("minute_of_day"),
        ),
    )


def test_clock_fixtures_match_the_shared_file() -> None:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    assert cases
    for case in cases:
        fires = plan_fires(
            now=_when(case["now"]),  # type: ignore[arg-type]
            start_at=_when(case.get("start_at")),
            due_at=_when(case.get("due_at")),
            closed=bool(case.get("closed")),
            rule=_rule(case["rule"]),
            snooze_until=_when(case.get("snooze_until")),
            overdue_dismissed=bool(case.get("overdue_dismissed")),
            catch_up=bool(case.get("catch_up")),
            rule_updated_at=_when(case.get("rule_updated_at")),
            overdue_limit=int(case.get("overdue_limit") or MAX_OVERDUE),
        )
        assert [fire_dict(fire) for fire in fires] == case["fires"], case["name"]


def test_duplicate_offsets_collapse_and_twenty_is_the_cap() -> None:
    collapsed = normalize_offsets(
        [
            Offset(1, "hour"),
            Offset(60, "minute"),
            Offset(1, "hour"),
            Offset(1, "day"),
        ]
    )
    assert collapsed == (Offset(1, "hour"), Offset(60, "minute"), Offset(1, "day"))
    with pytest.raises(InvalidReminderError):
        normalize_offsets([Offset(index + 1, "minute") for index in range(21)])


def test_a_saved_rule_stores_the_normalized_shape() -> None:
    rule = normalize_rule(
        Rule(
            due_offsets=(Offset(1, "hour"), Offset(1, "hour")),
            overdue=Overdue(kind="daily_at", minute_of_day=9 * 60),
        )
    )
    assert rule.due_offsets == (Offset(1, "hour"),)
    assert rule.overdue == Overdue(kind="daily_at", minute_of_day=540)
