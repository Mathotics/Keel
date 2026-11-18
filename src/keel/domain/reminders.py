"""Personal reminder clock. Wall times stay naive and local to the device."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from keel.domain.errors import InvalidReminderError

UNITS = ("minute", "hour", "day")
MAX_OFFSETS = 20
MAX_OVERDUE = 32
_MS = {"minute": 60, "hour": 3600, "day": 86400}
_UNIT_WORDS = {
    "minute": ("minute", "minutes"),
    "hour": ("hour", "hours"),
    "day": ("day", "days"),
}


@dataclass(frozen=True)
class Offset:
    amount: int
    unit: str


@dataclass(frozen=True)
class Overdue:
    kind: str
    amount: int = 1
    unit: str = "minute"
    minute_of_day: int | None = None


@dataclass(frozen=True)
class Rule:
    start_offsets: tuple[Offset, ...] = ()
    at_start: bool = False
    due_offsets: tuple[Offset, ...] = ()
    at_due: bool = False
    overdue: Overdue | None = None

    @property
    def blank(self) -> bool:
        return not (
            self.start_offsets
            or self.at_start
            or self.due_offsets
            or self.at_due
            or self.overdue is not None
        )


@dataclass(frozen=True)
class Fire:
    at: datetime
    reasons: tuple[str, ...]
    catch_up: bool


def wall(value: datetime) -> datetime:
    """Naive local clock time, truncated to the second."""
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.replace(microsecond=0)


def stamp(value: datetime | None) -> datetime | None:
    """UTC naive second, for comparing a saved row with a client's base."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(microsecond=0)


def same_stamp(left: datetime | None, right: datetime | None) -> bool:
    return stamp(left) == stamp(right)


def normalize_offsets(raw: list[Offset]) -> tuple[Offset, ...]:
    found: dict[tuple[str, int], Offset] = {}
    for item in raw:
        if item.unit not in UNITS or item.amount < 1:
            raise InvalidReminderError("Use minutes, hours, or days, at least 1.")
        found[(item.unit, item.amount)] = Offset(item.amount, item.unit)
    ordered = tuple(
        sorted(found.values(), key=lambda item: (_seconds(item), item.unit))
    )
    if len(ordered) > MAX_OFFSETS:
        raise InvalidReminderError("At most 20 reminders on one moment.")
    return ordered


def normalize_overdue(raw: Overdue | None) -> Overdue | None:
    if raw is None:
        return None
    if raw.kind == "daily_at":
        minute = raw.minute_of_day
        if minute is None or minute < 0 or minute > 1439:
            raise InvalidReminderError("Choose a time of day for the overdue reminder.")
        return Overdue(kind="daily_at", minute_of_day=minute)
    if raw.kind != "every_n" or raw.unit not in UNITS or raw.amount < 1:
        raise InvalidReminderError("Choose how often an overdue reminder repeats.")
    return Overdue(kind="every_n", amount=raw.amount, unit=raw.unit)


def normalize_rule(rule: Rule) -> Rule:
    return Rule(
        start_offsets=normalize_offsets(list(rule.start_offsets)),
        at_start=bool(rule.at_start),
        due_offsets=normalize_offsets(list(rule.due_offsets)),
        at_due=bool(rule.at_due),
        overdue=normalize_overdue(rule.overdue),
    )


def plan_fires(
    *,
    now: datetime,
    start_at: datetime | None,
    due_at: datetime | None,
    closed: bool,
    rule: Rule,
    snooze_until: datetime | None = None,
    overdue_dismissed: bool = False,
    catch_up: bool = False,
    rule_updated_at: datetime | None = None,
    overdue_limit: int = MAX_OVERDUE,
) -> list[Fire]:
    """Instants for one issue. A missing anchor adds nothing for that anchor."""
    if closed or rule.blank:
        return []
    moment = wall(now)
    saved = None if rule_updated_at is None else wall(rule_updated_at)
    events: list[tuple[datetime, str, bool, int]] = []
    if start_at is not None:
        events.extend(
            _one_shots(
                "start",
                wall(start_at),
                rule.start_offsets,
                rule.at_start,
                moment,
                catch_up,
                saved,
            )
        )
    if due_at is not None:
        events.extend(
            _one_shots(
                "due",
                wall(due_at),
                rule.due_offsets,
                rule.at_due,
                moment,
                catch_up,
                saved,
            )
        )
        events.extend(
            _overdue(
                due_at=wall(due_at),
                overdue=rule.overdue,
                now=moment,
                snooze_until=None if snooze_until is None else wall(snooze_until),
                dismissed=overdue_dismissed,
                catch_up=catch_up,
                saved_at=saved,
                limit=overdue_limit,
            )
        )
    events.sort(key=lambda item: (item[0], item[2], item[3]))
    return _group(events)


def fire_dict(fire: Fire) -> dict[str, object]:
    return {
        "at": fire.at.isoformat(),
        "reasons": list(fire.reasons),
        "catch_up": fire.catch_up,
    }


def _one_shots(
    kind: str,
    anchor: datetime,
    offsets: tuple[Offset, ...],
    at_anchor: bool,
    now: datetime,
    catch_up: bool,
    saved_at: datetime | None,
) -> list[tuple[datetime, str, bool, int]]:
    found: list[tuple[datetime, str, bool, int]] = []
    noun = "Starts" if kind == "start" else "Due"
    rank = 0 if kind == "start" else 2
    for offset in offsets:
        found.extend(
            _timed(
                anchor - timedelta(seconds=_seconds(offset)),
                _offset_label(noun, offset),
                now,
                catch_up,
                saved_at,
                rank,
            )
        )
    if at_anchor:
        found.extend(_timed(anchor, f"{noun} now", now, catch_up, saved_at, rank + 1))
    return found


def _timed(
    at: datetime,
    reason: str,
    now: datetime,
    catch_up: bool,
    saved_at: datetime | None,
    rank: int,
) -> list[tuple[datetime, str, bool, int]]:
    if at > now:
        return [(at, reason, False, rank)]
    if catch_up and (saved_at is None or saved_at < at):
        return [(at, reason, True, rank)]
    return []


def _overdue(
    *,
    due_at: datetime,
    overdue: Overdue | None,
    now: datetime,
    snooze_until: datetime | None,
    dismissed: bool,
    catch_up: bool,
    saved_at: datetime | None,
    limit: int,
) -> list[tuple[datetime, str, bool, int]]:
    if overdue is None or dismissed or limit < 1:
        return []
    first = _shift(due_at, overdue)
    events: list[tuple[datetime, str, bool, int]] = []
    if snooze_until is not None and snooze_until > now:
        cursor = snooze_until
    elif snooze_until is not None and snooze_until <= now:
        if catch_up:
            events.append((now, "Overdue", True, 4))
        cursor = _shift(now, overdue)
    elif first <= now:
        if catch_up and (saved_at is None or saved_at < first):
            events.append((now, "Overdue", True, 4))
        cursor = _shift(now, overdue)
    else:
        cursor = first
    scheduled = 0
    while scheduled < limit:
        events.append((cursor, "Overdue", False, 4))
        cursor = _shift(cursor, overdue)
        scheduled += 1
    return events


def _shift(moment: datetime, overdue: Overdue) -> datetime:
    if overdue.kind == "daily_at":
        minute = overdue.minute_of_day or 0
        midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        candidate = midnight + timedelta(minutes=minute)
        if candidate <= moment:
            candidate += timedelta(days=1)
        return candidate
    return moment + timedelta(seconds=_seconds(Offset(overdue.amount, overdue.unit)))


def _group(events: list[tuple[datetime, str, bool, int]]) -> list[Fire]:
    fires: list[Fire] = []
    for at, reason, caught, _rank in events:
        minute = at.replace(second=0, microsecond=0)
        if (
            fires
            and fires[-1].catch_up is caught
            and fires[-1].at.replace(second=0, microsecond=0) == minute
        ):
            if reason not in fires[-1].reasons:
                fires[-1] = Fire(
                    fires[-1].at,
                    (*fires[-1].reasons, reason),
                    caught,
                )
            continue
        fires.append(Fire(at, (reason,), caught))
    return fires


def _offset_label(noun: str, offset: Offset) -> str:
    singular, plural = _UNIT_WORDS[offset.unit]
    unit = singular if offset.amount == 1 else plural
    return f"{noun} in {offset.amount} {unit}"


def _seconds(offset: Offset) -> int:
    return offset.amount * _MS[offset.unit]
