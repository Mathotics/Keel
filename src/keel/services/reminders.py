"""Personal reminder rules. They are not issue fields and do not write history."""

import json
from datetime import datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from keel.db.models import Issue, Project, ReminderIssueState, ReminderRule
from keel.db.models.user import utc_now
from keel.domain.access import Permission
from keel.domain.enums import CLOSED_STATUSES
from keel.domain.errors import (
    InvalidReminderError,
    NotFoundError,
    ReminderConflictError,
)
from keel.domain.reminders import (
    MAX_OVERDUE,
    Offset,
    Overdue,
    Rule,
    normalize_rule,
    plan_fires,
    same_stamp,
    wall,
)
from keel.schemas.reminder import (
    BundleRead,
    EffectiveRead,
    FireRead,
    OverdueBody,
    RuleBody,
    RuleRead,
    RuleWrite,
    StateRead,
)
from keel.services import issues as issue_service
from keel.services.access import Access, project_ids_holding


def get_default(session: Session, user_id: int) -> RuleRead | None:
    row = _find(session, user_id, "default", None, None)
    return None if row is None else _read(row)


def save_default(session: Session, user_id: int, draft: RuleWrite) -> RuleRead:
    return _read(_save(session, user_id, "default", None, None, draft))


def get_series_rule(session: Session, user_id: int, series_id: int) -> RuleRead | None:
    row = _find(session, user_id, "series", series_id, None)
    return None if row is None else _read(row)


def save_series_rule(
    session: Session,
    user_id: int,
    series_id: int,
    draft: RuleWrite,
) -> RuleRead:
    return _read(_save(session, user_id, "series", series_id, None, draft))


def delete_series_rule(
    session: Session,
    user_id: int,
    series_id: int,
    base_updated_at: datetime | None,
) -> None:
    _delete(session, user_id, "series", series_id, None, base_updated_at)


def effective_issue(session: Session, user_id: int, issue: Issue) -> EffectiveRead:
    own = _find(session, user_id, "issue", None, issue.id)
    source, rule = _resolve(session, user_id, issue, own)
    state = _state(session, user_id, issue.id)
    closed = issue.status in CLOSED_STATUSES
    return EffectiveRead(
        source=source,
        rule=None if rule is None else _body(rule),
        own=None if own is None else _read(own),
        start_missing=issue.start_at is None,
        due_missing=issue.due_at is None,
        closed=closed,
        snooze_until=None if state is None else state.snooze_until,
        overdue_dismissed=False if state is None else state.overdue_dismissed,
        state_updated_at=None if state is None else state.updated_at,
    )


def save_issue_rule(
    session: Session,
    user_id: int,
    issue_id: int,
    draft: RuleWrite,
) -> RuleRead:
    return _read(_save(session, user_id, "issue", None, issue_id, draft))


def delete_issue_rule(
    session: Session,
    user_id: int,
    issue_id: int,
    base_updated_at: datetime | None,
) -> None:
    _delete(session, user_id, "issue", None, issue_id, base_updated_at)


def snooze(
    session: Session,
    user_id: int,
    issue_id: int,
    until: datetime,
    base_updated_at: datetime | None,
) -> StateRead:
    return _touch_state(
        session,
        user_id,
        issue_id,
        base_updated_at,
        snooze_until=wall(until),
    )


def dismiss_overdue(
    session: Session,
    user_id: int,
    issue_id: int,
    base_updated_at: datetime | None,
) -> StateRead:
    return _touch_state(
        session,
        user_id,
        issue_id,
        base_updated_at,
        overdue_dismissed=True,
    )


def resume_overdue(
    session: Session,
    user_id: int,
    issue_id: int,
    base_updated_at: datetime | None,
) -> StateRead:
    return _touch_state(
        session,
        user_id,
        issue_id,
        base_updated_at,
        overdue_dismissed=False,
    )


def bundle(session: Session, user_id: int) -> BundleRead:
    rows = session.scalars(
        select(ReminderRule).where(ReminderRule.user_id == user_id)
    ).all()
    states = session.scalars(
        select(ReminderIssueState).where(ReminderIssueState.user_id == user_id)
    ).all()
    default = next((row for row in rows if row.scope == "default"), None)
    return BundleRead(
        default=None if default is None else _read(default),
        series=[_read(row) for row in rows if row.scope == "series"],
        issues=[_read(row) for row in rows if row.scope == "issue"],
        states=[_state_read(row) for row in states],
    )


def schedule(
    session: Session,
    access: Access,
    user_id: int,
    *,
    now: datetime | None = None,
    catch_up: bool = True,
) -> list[FireRead]:
    moment = wall(now or datetime.now())
    rows = session.scalars(
        select(ReminderRule).where(ReminderRule.user_id == user_id)
    ).all()
    by_issue = {row.issue_id: row for row in rows if row.scope == "issue"}
    by_series = {row.series_id: row for row in rows if row.scope == "series"}
    default = next((row for row in rows if row.scope == "default"), None)
    if not by_issue and not by_series and (default is None or _rule(default).blank):
        return []
    states = {
        row.issue_id: row
        for row in session.scalars(
            select(ReminderIssueState).where(ReminderIssueState.user_id == user_id)
        ).all()
    }
    visible = project_ids_holding(session, access, Permission.VIEW_ISSUES)
    clauses: list[ColumnElement[bool]] = []
    if by_issue:
        clauses.append(Issue.id.in_(by_issue))
    if by_series:
        clauses.append(Issue.series_id.in_(by_series))
    if default is not None and not _rule(default).blank:
        clauses.append(or_(Issue.start_at.is_not(None), Issue.due_at.is_not(None)))
    if not clauses:
        return []
    statement = (
        select(Issue, Project)
        .join(Project, Project.id == Issue.project_id)
        .where(or_(*clauses))
        .where(Issue.status.notin_(tuple(CLOSED_STATUSES)))
    )
    if visible is not None:
        if not visible:
            return []
        statement = statement.where(Issue.project_id.in_(visible))
    fires: list[FireRead] = []
    for issue, project in session.execute(statement).all():
        source_row = _row_for(issue, default, by_series, by_issue)
        if source_row is None:
            continue
        rule = _rule(source_row)
        if rule.blank:
            continue
        state = states.get(issue.id)
        planned = plan_fires(
            now=moment,
            start_at=issue.start_at,
            due_at=issue.due_at,
            closed=False,
            rule=rule,
            snooze_until=None if state is None else state.snooze_until,
            overdue_dismissed=False if state is None else state.overdue_dismissed,
            catch_up=catch_up,
            rule_updated_at=source_row.updated_at,
            overdue_limit=MAX_OVERDUE,
        )
        key = issue_service.issue_key(issue, project)
        for fire in planned:
            fires.append(
                FireRead(
                    issue_id=issue.id,
                    issue_key=key,
                    issue_title=issue.title,
                    at=fire.at,
                    reasons=list(fire.reasons),
                    catch_up=fire.catch_up,
                )
            )
    fires.sort(key=lambda item: (item.at, item.issue_id, item.catch_up))
    return fires


def rule_from_lists(
    start_amounts: list[str],
    start_units: list[str],
    at_start: bool,
    due_amounts: list[str],
    due_units: list[str],
    at_due: bool,
    overdue_kind: str,
    overdue_amount: str,
    overdue_unit: str,
    overdue_clock: str,
    base_updated_at: str,
) -> RuleWrite:
    overdue = _overdue_from_form(
        overdue_kind,
        overdue_amount,
        overdue_unit,
        overdue_clock,
    )
    return RuleWrite(
        start_offsets=_pairs(start_amounts, start_units),
        at_start=at_start,
        due_offsets=_pairs(due_amounts, due_units),
        at_due=at_due,
        overdue=overdue,
        base_updated_at=_parse_stamp(base_updated_at),
    )


def _save(
    session: Session,
    user_id: int,
    scope: str,
    series_id: int | None,
    issue_id: int | None,
    draft: RuleWrite,
) -> ReminderRule:
    rule = normalize_rule(_from_body(draft))
    row = _find(session, user_id, scope, series_id, issue_id)
    if row is None:
        if draft.base_updated_at is not None:
            raise ReminderConflictError(
                "This reminder changed on the server.",
                server=None,
            )
        row = ReminderRule(
            user_id=user_id,
            scope=scope,
            series_id=series_id,
            issue_id=issue_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(row)
    elif not same_stamp(row.updated_at, draft.base_updated_at):
        raise ReminderConflictError(
            "This reminder changed on the server.",
            server=_read(row).model_dump(mode="json"),
        )
    _apply(row, rule)
    row.updated_at = utc_now()
    session.flush()
    return row


def _delete(
    session: Session,
    user_id: int,
    scope: str,
    series_id: int | None,
    issue_id: int | None,
    base_updated_at: datetime | None,
) -> None:
    row = _find(session, user_id, scope, series_id, issue_id)
    if row is None:
        if base_updated_at is not None:
            raise ReminderConflictError(
                "This reminder changed on the server.",
                server=None,
            )
        raise NotFoundError("No reminder to reset.")
    if not same_stamp(row.updated_at, base_updated_at):
        raise ReminderConflictError(
            "This reminder changed on the server.",
            server=_read(row).model_dump(mode="json"),
        )
    session.delete(row)
    session.flush()


def _touch_state(
    session: Session,
    user_id: int,
    issue_id: int,
    base_updated_at: datetime | None,
    *,
    snooze_until: datetime | None = None,
    overdue_dismissed: bool | None = None,
) -> StateRead:
    row = _state(session, user_id, issue_id)
    if row is None:
        if base_updated_at is not None:
            raise ReminderConflictError(
                "This reminder changed on the server.",
                server=None,
            )
        row = ReminderIssueState(
            user_id=user_id,
            issue_id=issue_id,
            updated_at=utc_now(),
        )
        session.add(row)
    elif not same_stamp(row.updated_at, base_updated_at):
        raise ReminderConflictError(
            "This reminder changed on the server.",
            server=_state_read(row).model_dump(mode="json"),
        )
    if snooze_until is not None:
        row.snooze_until = snooze_until
    if overdue_dismissed is not None:
        row.overdue_dismissed = overdue_dismissed
    row.updated_at = utc_now()
    session.flush()
    return _state_read(row)


def _resolve(
    session: Session,
    user_id: int,
    issue: Issue,
    own: ReminderRule | None,
) -> tuple[str, Rule | None]:
    if own is not None:
        return "issue", _rule(own)
    if issue.series_id is not None:
        series_rule = _find(session, user_id, "series", issue.series_id, None)
        if series_rule is not None:
            return "series", _rule(series_rule)
    default = _find(session, user_id, "default", None, None)
    if default is not None:
        return "default", _rule(default)
    return "none", None


def _row_for(
    issue: Issue,
    default: ReminderRule | None,
    by_series: dict[int | None, ReminderRule],
    by_issue: dict[int | None, ReminderRule],
) -> ReminderRule | None:
    own = by_issue.get(issue.id)
    if own is not None:
        return own
    if issue.series_id is not None and issue.series_id in by_series:
        return by_series[issue.series_id]
    return default


def _find(
    session: Session,
    user_id: int,
    scope: str,
    series_id: int | None,
    issue_id: int | None,
) -> ReminderRule | None:
    statement = select(ReminderRule).where(
        ReminderRule.user_id == user_id,
        ReminderRule.scope == scope,
    )
    if series_id is None:
        statement = statement.where(ReminderRule.series_id.is_(None))
    else:
        statement = statement.where(ReminderRule.series_id == series_id)
    if issue_id is None:
        statement = statement.where(ReminderRule.issue_id.is_(None))
    else:
        statement = statement.where(ReminderRule.issue_id == issue_id)
    return session.scalars(statement).first()


def _state(session: Session, user_id: int, issue_id: int) -> ReminderIssueState | None:
    return session.scalars(
        select(ReminderIssueState).where(
            ReminderIssueState.user_id == user_id,
            ReminderIssueState.issue_id == issue_id,
        )
    ).first()


def _apply(row: ReminderRule, rule: Rule) -> None:
    row.start_offsets = json.dumps(
        [{"amount": item.amount, "unit": item.unit} for item in rule.start_offsets]
    )
    row.at_start = rule.at_start
    row.due_offsets = json.dumps(
        [{"amount": item.amount, "unit": item.unit} for item in rule.due_offsets]
    )
    row.at_due = rule.at_due
    if rule.overdue is None:
        row.overdue = None
        return
    payload: dict[str, object] = {"kind": rule.overdue.kind}
    if rule.overdue.kind == "daily_at":
        payload["minute_of_day"] = rule.overdue.minute_of_day
    else:
        payload["amount"] = rule.overdue.amount
        payload["unit"] = rule.overdue.unit
    row.overdue = json.dumps(payload)


def _rule(row: ReminderRule) -> Rule:
    return Rule(
        start_offsets=tuple(_offsets(row.start_offsets)),
        at_start=row.at_start,
        due_offsets=tuple(_offsets(row.due_offsets)),
        at_due=row.at_due,
        overdue=_overdue(row.overdue),
    )


def _offsets(raw: str) -> list[Offset]:
    try:
        loaded = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [Offset(int(item["amount"]), str(item["unit"])) for item in loaded]


def _overdue(raw: str | None) -> Overdue | None:
    if not raw:
        return None
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if loaded.get("kind") == "daily_at":
        return Overdue(kind="daily_at", minute_of_day=int(loaded["minute_of_day"]))
    return Overdue(
        kind="every_n",
        amount=int(loaded["amount"]),
        unit=str(loaded["unit"]),
    )


def _from_body(body: RuleBody) -> Rule:
    overdue = None
    if body.overdue is not None:
        overdue = Overdue(
            kind=body.overdue.kind,
            amount=body.overdue.amount or 1,
            unit=body.overdue.unit or "minute",
            minute_of_day=body.overdue.minute_of_day,
        )
    return Rule(
        start_offsets=tuple(
            Offset(item.amount, item.unit) for item in body.start_offsets
        ),
        at_start=body.at_start,
        due_offsets=tuple(Offset(item.amount, item.unit) for item in body.due_offsets),
        at_due=body.at_due,
        overdue=overdue,
    )


def _body(rule: Rule) -> RuleBody:
    overdue = None
    if rule.overdue is not None:
        overdue = OverdueBody(
            kind=rule.overdue.kind,
            amount=None if rule.overdue.kind == "daily_at" else rule.overdue.amount,
            unit=None if rule.overdue.kind == "daily_at" else rule.overdue.unit,
            minute_of_day=rule.overdue.minute_of_day,
        )
    return RuleBody(
        start_offsets=[
            {"amount": item.amount, "unit": item.unit} for item in rule.start_offsets
        ],
        at_start=rule.at_start,
        due_offsets=[
            {"amount": item.amount, "unit": item.unit} for item in rule.due_offsets
        ],
        at_due=rule.at_due,
        overdue=overdue,
    )


def _read(row: ReminderRule) -> RuleRead:
    body = _body(_rule(row))
    return RuleRead(
        id=row.id,
        scope=row.scope,
        series_id=row.series_id,
        issue_id=row.issue_id,
        updated_at=row.updated_at,
        start_offsets=body.start_offsets,
        at_start=body.at_start,
        due_offsets=body.due_offsets,
        at_due=body.at_due,
        overdue=body.overdue,
    )


def _state_read(row: ReminderIssueState) -> StateRead:
    return StateRead(
        issue_id=row.issue_id,
        snooze_until=row.snooze_until,
        overdue_dismissed=row.overdue_dismissed,
        updated_at=row.updated_at,
    )


def _pairs(amounts: list[str], units: list[str]) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for amount, unit in zip(amounts, units, strict=False):
        text = amount.strip()
        if not text:
            continue
        if not text.isdigit() or int(text) < 1 or unit not in {"minute", "hour", "day"}:
            raise InvalidReminderError("Use minutes, hours, or days, at least 1.")
        found.append({"amount": int(text), "unit": unit})
    return found


def _overdue_from_form(
    kind: str,
    amount: str,
    unit: str,
    clock: str,
) -> OverdueBody | None:
    chosen = kind.strip()
    if not chosen or chosen == "off":
        return None
    if chosen == "daily_at":
        parts = clock.strip().split(":")
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise InvalidReminderError("Choose a time of day for the overdue reminder.")
        minute = int(parts[0]) * 60 + int(parts[1])
        if minute < 0 or minute > 1439:
            raise InvalidReminderError("Choose a time of day for the overdue reminder.")
        return OverdueBody(kind="daily_at", minute_of_day=minute)
    if (
        not amount.strip().isdigit()
        or int(amount) < 1
        or unit
        not in {
            "minute",
            "hour",
            "day",
        }
    ):
        raise InvalidReminderError("Choose how often an overdue reminder repeats.")
    return OverdueBody(kind="every_n", amount=int(amount), unit=unit)


def _parse_stamp(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidReminderError("That reminder stamp is not a time.") from exc
