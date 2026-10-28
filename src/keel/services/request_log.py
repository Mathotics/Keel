"""Request log: capture what a signed-in call changed, list it, and trim it."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from time import monotonic

from sqlalchemy import Select, delete, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import instance_state

from keel.db.models import (
    ApiToken,
    AuthSession,
    Board,
    Comment,
    Dependency,
    Issue,
    IssueHistory,
    IssueLabel,
    Label,
    Project,
    RequestLog,
    Series,
    SeriesLabel,
    SeriesSkip,
    Sprint,
    User,
)
from keel.domain.enums import label
from keel.services import history as history_service
from keel.settings import KeelSettings

PAGE_SIZE = 50
_NOTE_LIMIT = 2000
_ROW_OVERHEAD = 32
_SIZE_CHECK_SECONDS = 60.0
_size_lock = threading.Lock()
_last_size_check = 0.0
_PATH_LIMIT = 2048
WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
LOG_PATH = "/admin/log"
_PERSON_RE = re.compile(r"[1-9][0-9]*")
# Markdown bodies are too long to quote in a log note.
_OPAQUE_TEXT_FIELDS = frozenset(
    {
        history_service.FIELD_DESCRIPTION,
        history_service.FIELD_DEFINITION_OF_DONE,
    },
)


@dataclass
class _Capture:
    notes: list[str]
    history_issues: set[int]


_capture: ContextVar[_Capture | None] = ContextVar(
    "keel_request_log_capture",
    default=None,
)
_suppress: ContextVar[int] = ContextVar("keel_request_log_suppress", default=0)
_listener_installed = False


@dataclass(frozen=True)
class RequestLogQuery:
    user_id: int | None
    start: date | None
    end: date | None
    span: str
    changes_only: bool
    result: str
    path: str
    page: int

    @property
    def narrowed(self) -> bool:
        return bool(
            self.user_id is not None
            or self.start is not None
            or self.end is not None
            or self.changes_only
            or self.result != "all"
            or self.path
        )


@dataclass(frozen=True)
class RequestLogPage:
    rows: Sequence[RequestLog]
    page: int
    total: int
    has_older: bool
    has_newer: bool


def install_request_log_listener() -> None:
    global _listener_installed
    if _listener_installed:
        return
    event.listen(Session, "before_flush", _before_flush)
    _listener_installed = True


def begin_capture() -> Token[_Capture | None]:
    return _capture.set(_Capture(notes=[], history_issues=set()))


def finish_capture(token: Token[_Capture | None]) -> str | None:
    capture = _capture.get()
    try:
        if capture is None:
            return None
        return _join_notes(capture.notes)
    finally:
        try:
            _capture.reset(token)
        except (ValueError, RuntimeError):
            _capture.set(None)


@contextmanager
def suppress_change_notes() -> Iterator[None]:
    """Hide catch-up work (auto-sprint) from the note on the person's request."""
    token = _suppress.set(_suppress.get() + 1)
    try:
        yield
    finally:
        try:
            _suppress.reset(token)
        except (ValueError, RuntimeError):
            _suppress.set(0)


def skip_request_path(path: str) -> bool:
    """Static files, health, favicon, and the log page itself are not entries."""
    if path in {"/health", "/favicon.ico", LOG_PATH, f"{LOG_PATH}/"}:
        return True
    return path == "/assets" or path.startswith("/assets/")


def keep_change_note(method: str, status_code: int, note: str | None) -> str | None:
    """A note belongs on a write that completed. Failures and reads stay blank."""
    if not note:
        return None
    if method.upper() not in WRITE_METHODS:
        return None
    if status_code >= 400:
        return None
    return note


def record_request(
    session: Session,
    *,
    user_id: int,
    actor_name: str,
    method: str,
    path: str,
    status_code: int,
    change_note: str | None,
    settings: KeelSettings,
) -> RequestLog:
    clean_path = path.split("?", 1)[0][:_PATH_LIMIT] or "/"
    row = RequestLog(
        user_id=user_id,
        actor_name=actor_name[:100],
        method=method.upper()[:16],
        path=clean_path,
        status_code=status_code,
        change_note=change_note,
    )
    session.add(row)
    session.flush()
    enforce_retention(session, settings, check_size=_size_check_due())
    return row


def _size_check_due() -> bool:
    """The size scan reads every log row. Once a minute is enough."""
    global _last_size_check
    now = monotonic()
    with _size_lock:
        if now - _last_size_check < _SIZE_CHECK_SECONDS:
            return False
        _last_size_check = now
        return True


def enforce_retention(
    session: Session,
    settings: KeelSettings,
    *,
    check_size: bool = True,
) -> None:
    """Drop the oldest rows past the age limit, then past the size limit."""
    days = max(settings.request_log_max_age_days, 0)
    if days:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        session.execute(delete(RequestLog).where(RequestLog.created_at < cutoff))
        session.flush()
    if not check_size:
        return
    budget = max(settings.request_log_max_bytes, 0)
    if not budget:
        return
    while stored_bytes(session) > budget:
        oldest_id = session.scalar(
            select(RequestLog.id)
            .order_by(RequestLog.created_at, RequestLog.id)
            .limit(1),
        )
        if oldest_id is None:
            return
        session.execute(delete(RequestLog).where(RequestLog.id == oldest_id))
        session.flush()


def stored_bytes(session: Session) -> int:
    """Text length of the log's own columns, plus a small per-row overhead."""
    total = session.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.length(RequestLog.method)
                    + func.length(RequestLog.path)
                    + func.length(RequestLog.actor_name)
                    + func.length(func.coalesce(RequestLog.change_note, ""))
                    + _ROW_OVERHEAD
                ),
                0,
            ),
        ),
    )
    return int(total or 0)


def parse_query(
    *,
    person: str | None = None,
    start: str | None = None,
    end: str | None = None,
    span: str | None = None,
    kind: str | None = None,
    result: str | None = None,
    path: str | None = None,
    page: str | None = None,
    today: date | None = None,
) -> RequestLogQuery:
    current = today or datetime.now(UTC).date()
    chosen = (span or "").strip()
    window_start: date | None
    window_end: date | None
    if chosen == "today":
        window_start, window_end = current, current
    elif chosen == "7":
        window_start, window_end = current - timedelta(days=6), current
    elif chosen == "30":
        window_start, window_end = current - timedelta(days=29), current
    else:
        chosen = ""
        window_start = _parse_date(start)
        window_end = _parse_date(end)
        if (
            window_start is not None
            and window_end is not None
            and window_start > window_end
        ):
            window_start, window_end = window_end, window_start
    outcome = (result or "all").strip().lower()
    if outcome not in {"all", "succeeded", "failed"}:
        outcome = "all"
    return RequestLogQuery(
        user_id=_parse_person(person),
        start=window_start,
        end=window_end,
        span=chosen,
        changes_only=(kind or "").strip() == "changes",
        result=outcome,
        path=(path or "").strip()[:200],
        page=_parse_page(page),
    )


def list_requests(
    session: Session,
    query: RequestLogQuery,
    settings: KeelSettings,
) -> RequestLogPage:
    enforce_retention(session, settings)
    filtered = _filtered(query)
    total = int(
        session.scalar(select(func.count()).select_from(filtered.subquery())) or 0,
    )
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    page = min(query.page, pages)
    offset = (page - 1) * PAGE_SIZE
    rows = session.scalars(
        filtered.order_by(RequestLog.created_at.desc(), RequestLog.id.desc())
        .offset(offset)
        .limit(PAGE_SIZE),
    ).all()
    return RequestLogPage(
        rows=rows,
        page=page,
        total=total,
        has_older=offset + len(rows) < total,
        has_newer=page > 1 and total > 0,
    )


def _filtered(query: RequestLogQuery) -> Select[tuple[RequestLog]]:
    stmt = select(RequestLog)
    if query.user_id is not None:
        stmt = stmt.where(RequestLog.user_id == query.user_id)
    if query.start is not None:
        stmt = stmt.where(
            RequestLog.created_at >= datetime.combine(query.start, time.min),
        )
    if query.end is not None:
        stmt = stmt.where(
            RequestLog.created_at
            < datetime.combine(query.end + timedelta(days=1), time.min),
        )
    if query.changes_only:
        stmt = stmt.where(RequestLog.method.in_(tuple(WRITE_METHODS)))
    if query.result == "succeeded":
        stmt = stmt.where(RequestLog.status_code < 400)
    elif query.result == "failed":
        stmt = stmt.where(RequestLog.status_code >= 400)
    if query.path:
        stmt = stmt.where(
            func.lower(RequestLog.path).like(_like(query.path.lower()), escape="\\"),
        )
    return stmt


def _before_flush(
    session: Session,
    _flush_context: object,
    _instances: Sequence[object] | None = None,
) -> None:
    capture = _capture.get()
    if capture is None or _suppress.get():
        return
    for obj in list(session.new):
        if isinstance(obj, IssueHistory):
            capture.history_issues.add(obj.issue_id)
            capture.notes.append(_history_line(session, obj))
    for obj in list(session.new):
        _collect(session, capture, obj, "created")
    for obj in list(session.deleted):
        _collect(session, capture, obj, "deleted")
    for obj in list(session.dirty):
        _collect(session, capture, obj, "updated")


def _collect(session: Session, capture: _Capture, obj: object, verb: str) -> None:
    if isinstance(obj, IssueHistory | RequestLog | AuthSession):
        return
    note = _describe(session, capture, obj, verb)
    if note:
        capture.notes.append(note)


def _describe(
    session: Session,
    capture: _Capture,
    obj: object,
    verb: str,
) -> str | None:
    if isinstance(obj, Issue):
        if verb == "updated" and obj.id in capture.history_issues:
            return None
        if verb == "updated" and not _meaningful(obj, set()):
            return None
        return f"{_issue_key(session, obj)} {verb}"
    if isinstance(obj, Comment):
        key = history_service.parent_label(session, obj.issue_id)
        if verb == "deleted":
            return f"{key} comment removed"
        if verb == "created":
            return f"{key} comment added"
        return None
    if isinstance(obj, Project):
        if verb == "updated" and not _meaningful(obj, {"issue_seq"}):
            return None
        return f"project {obj.key} {verb}"
    if isinstance(obj, Board):
        return f"board {obj.name} {verb}"
    if isinstance(obj, Sprint):
        return f"sprint {obj.name} {verb}"
    if isinstance(obj, Series):
        return f"series {obj.title} {verb}"
    if isinstance(obj, SeriesSkip):
        series = session.get(Series, obj.series_id)
        title = series.title if series is not None else "series"
        if verb == "deleted":
            return f"series {title} skip removed"
        return f"series {title} skip {obj.occurrence_on.isoformat()}"
    if isinstance(obj, User):
        return _user_note(obj, verb)
    if isinstance(obj, ApiToken):
        return _token_note(obj, verb)
    if isinstance(obj, Dependency):
        source = history_service.parent_label(session, obj.source_id)
        target = history_service.parent_label(session, obj.target_id)
        phrase = f"{source} {label(obj.kind).lower()} {target}"
        if verb == "deleted":
            return f"{phrase} removed"
        if verb == "created":
            return phrase
        return None
    if isinstance(obj, Label):
        if verb == "deleted":
            return f"label {obj.name} removed"
        if verb == "created":
            return f"label {obj.name} added"
        return None
    if isinstance(obj, IssueLabel):
        if obj.issue_id in capture.history_issues:
            return None
        key = history_service.parent_label(session, obj.issue_id)
        return f"{key} labels changed"
    if isinstance(obj, SeriesLabel):
        series = session.get(Series, obj.series_id)
        title = series.title if series is not None else "series"
        return f"series {title} labels changed"
    return None


def _user_note(user: User, verb: str) -> str | None:
    if verb == "created":
        return f"user {user.display_name} added"
    if verb == "deleted":
        return f"user {user.display_name} deleted"
    keys = _changed_keys(user)
    parts: list[str] = []
    if "display_name" in keys:
        history = instance_state(user).attrs.display_name.history
        old = history.deleted[0] if history.deleted else user.display_name
        parts.append(f"user {old} renamed to {user.display_name}")
    if "username" in keys:
        parts.append(f"user {user.display_name} username changed")
    if "password_hash" in keys:
        parts.append(f"user {user.display_name} password changed")
    if not parts:
        return None
    return "; ".join(parts)


def _token_note(token: ApiToken, verb: str) -> str | None:
    if verb == "created":
        return f"API token {token.label} created"
    if verb == "deleted":
        return f"API token {token.label} revoked"
    if "revoked_at" in _changed_keys(token) and token.revoked_at is not None:
        return f"API token {token.label} revoked"
    return None


def _history_line(session: Session, event_row: IssueHistory) -> str:
    key = history_service.parent_label(session, event_row.issue_id)
    if event_row.field in _OPAQUE_TEXT_FIELDS:
        return f"{key} {event_row.field} changed"
    line = f"{key} {event_row.field} {event_row.from_value} → {event_row.to_value}"
    if len(line) > 300:
        return line[:299] + "…"
    return line


def _issue_key(session: Session, issue: Issue) -> str:
    project = session.get(Project, issue.project_id)
    if project is None:
        return "issue"
    return f"{project.key}-{issue.number}"


def _meaningful(obj: object, ignored: set[str]) -> bool:
    return bool(_changed_keys(obj) - ignored - {"updated_at"})


def _changed_keys(obj: object) -> set[str]:
    state = instance_state(obj)
    changed: set[str] = set()
    for attr in state.mapper.column_attrs:
        if state.attrs[attr.key].history.has_changes():
            changed.add(attr.key)
    return changed


def _join_notes(notes: Sequence[str]) -> str | None:
    seen: set[str] = set()
    lines: list[str] = []
    for note in notes:
        if not note or note in seen:
            continue
        seen.add(note)
        lines.append(note)
    if not lines:
        return None
    text = "; ".join(lines)
    if len(text) > _NOTE_LIMIT:
        return text[: _NOTE_LIMIT - 1] + "…"
    return text


def _parse_date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_person(value: str | None) -> int | None:
    if not value or not _PERSON_RE.fullmatch(value.strip()):
        return None
    return int(value.strip())


def _parse_page(value: str | None) -> int:
    if not value or not value.strip().isdigit():
        return 1
    return min(max(int(value.strip()), 1), 10_000)


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


install_request_log_listener()
