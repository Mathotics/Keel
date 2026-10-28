from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import (
    ApiToken,
    Comment,
    Dependency,
    IssueLabel,
    Label,
    RequestLog,
    Series,
    SeriesLabel,
    SeriesSkip,
    Sprint,
    User,
)
from keel.db.models.user import utc_now
from keel.domain.enums import (
    DependencyKind,
    IssueStatus,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
)
from keel.services import issues as issue_service
from keel.services import projects as project_service
from keel.services import users as user_service
from keel.services.request_log import (
    begin_capture,
    enforce_retention,
    finish_capture,
    install_request_log_listener,
    keep_change_note,
    parse_query,
    skip_request_path,
    stored_bytes,
    suppress_change_notes,
)
from keel.settings import KeelSettings


def test_skip_paths_leave_out_noise() -> None:
    assert skip_request_path("/health")
    assert skip_request_path("/favicon.ico")
    assert skip_request_path("/assets/brand.css")
    assert skip_request_path("/admin/log")
    assert skip_request_path("/admin/log/")
    assert not skip_request_path("/projects")
    assert not skip_request_path("/api/v1/issues")


def test_change_note_stays_on_successful_writes_only() -> None:
    assert keep_change_note("POST", 201, "KEEL-1 created") == "KEEL-1 created"
    assert keep_change_note("POST", 303, "KEEL-1 created") == "KEEL-1 created"
    assert keep_change_note("POST", 409, "KEEL-1 created") is None
    assert keep_change_note("GET", 200, "KEEL-1 created") is None
    assert keep_change_note("PATCH", 200, None) is None
    assert keep_change_note("patch", 200, "KEEL-1 status To Do → In Progress") == (
        "KEEL-1 status To Do → In Progress"
    )


def test_parse_query_applies_spans_and_rejects_junk() -> None:
    today = date(2026, 10, 14)
    query = parse_query(
        person="3",
        span="7",
        kind="changes",
        result="nope",
        path=" /api ",
        page="2",
        start="2020-01-01",
        today=today,
    )
    assert query.user_id == 3
    assert query.start == date(2026, 10, 8)
    assert query.end == today
    assert query.span == "7"
    assert query.changes_only is True
    assert query.result == "all"
    assert query.path == "/api"
    assert query.page == 2
    assert query.narrowed is True

    today_query = parse_query(span="today", today=today)
    assert today_query.start == today and today_query.end == today
    month = parse_query(span="30", today=today)
    assert month.start == date(2026, 9, 15)
    assert parse_query(start="not-a-date", today=today).start is None

    custom = parse_query(start="2026-10-02", end="2026-10-01", today=today)
    assert custom.start == date(2026, 10, 1)
    assert custom.end == date(2026, 10, 2)
    assert custom.span == ""
    assert parse_query(person="0", page="nope", result="failed").user_id is None
    assert parse_query(person="0", page="nope", result="failed").page == 1
    assert parse_query(person="0", page="nope", result="failed").result == "failed"
    assert parse_query().narrowed is False


def test_capture_names_a_new_project_and_issue(session: Session) -> None:
    token = begin_capture()
    project = project_service.create_project(session, "KEEL", "Keel")
    note = finish_capture(token)
    assert note is not None
    assert "project KEEL created" in note
    assert "board KEEL board created" in note

    token = begin_capture()
    issue = issue_service.create_issue(session, project.id, IssueType.STORY, "A story")
    created = finish_capture(token)
    assert created == "KEEL-1 created"

    token = begin_capture()
    issue_service.update_issue(session, issue.id, status=IssueStatus.IN_PROGRESS)
    changed = finish_capture(token)
    assert changed == "KEEL-1 status To Do → In Progress"


def test_capture_hides_password_material(session: Session) -> None:
    user = User(username="ada", display_name="Ada")
    session.add(user)
    session.flush()
    token = begin_capture()
    user_service.set_password(session, user, "a-real-password-1")
    note = finish_capture(token)
    assert note == "user Ada password changed"
    assert "a-real-password-1" not in (note or "")
    assert "argon" not in (note or "")


def test_suppressed_work_is_not_a_change_note(session: Session) -> None:
    token = begin_capture()
    with suppress_change_notes():
        project_service.create_project(session, "KEEL", "Keel")
    assert finish_capture(token) is None


def test_age_limit_drops_old_rows_and_zero_keeps_them(session: Session) -> None:
    old = RequestLog(
        actor_name="Ada",
        method="GET",
        path="/old",
        status_code=200,
        created_at=datetime.now(UTC) - timedelta(days=31),
    )
    new = RequestLog(actor_name="Ada", method="GET", path="/new", status_code=200)
    session.add_all([old, new])
    session.commit()

    enforce_retention(
        session,
        KeelSettings(
            _env_file=None,
            request_log_max_age_days=30,
            request_log_max_bytes=0,
        ),
    )
    session.commit()
    assert [row.path for row in session.scalars(select(RequestLog))] == ["/new"]


def test_finish_capture_can_be_closed_twice() -> None:
    install_request_log_listener()
    token = begin_capture()
    assert finish_capture(token) is None
    assert finish_capture(token) is None


def test_capture_describes_records_without_secrets(session: Session) -> None:
    project = project_service.create_project(session, "KEEL", "Keel")
    issue = issue_service.create_issue(session, project.id, IssueType.STORY, "A story")
    other = issue_service.create_issue(session, project.id, IssueType.STORY, "Other")
    user = User(username="ada", display_name="Ada")
    session.add(user)
    session.flush()

    token = begin_capture()
    session.add(Comment(issue_id=issue.id, author_id=user.id, body="secret comment"))
    session.flush()
    comment_note = finish_capture(token)
    assert comment_note == "KEEL-1 comment added"
    assert "secret comment" not in (comment_note or "")

    token = begin_capture()
    session.add(
        Dependency(
            source_id=issue.id,
            target_id=other.id,
            kind=DependencyKind.BLOCKS,
        ),
    )
    session.flush()
    assert finish_capture(token) == "KEEL-1 blocks KEEL-2"

    token = begin_capture()
    session.add(Sprint(project_id=project.id, name="Week 1"))
    session.flush()
    assert finish_capture(token) == "sprint Week 1 created"

    token = begin_capture()
    label = Label(name="bug")
    session.add(label)
    session.flush()
    session.add(IssueLabel(issue_id=issue.id, label_id=label.id))
    session.flush()
    labeled = finish_capture(token)
    assert labeled is not None
    assert "label bug added" in labeled
    assert "KEEL-1 labels changed" in labeled

    token = begin_capture()
    access = ApiToken(
        user_id=user.id,
        label="laptop",
        token_prefix="abcd",
        token_hash="hash-value-not-for-the-log",
    )
    session.add(access)
    session.flush()
    token_note = finish_capture(token)
    assert token_note == "API token laptop created"
    assert "hash-value-not-for-the-log" not in (token_note or "")

    token = begin_capture()
    access.last_used_at = utc_now()
    session.flush()
    assert finish_capture(token) is None

    token = begin_capture()
    access.revoked_at = utc_now()
    session.flush()
    assert finish_capture(token) == "API token laptop revoked"

    token = begin_capture()
    user.display_name = "Ada Lovelace"
    user.username = "ada-l"
    session.flush()
    renamed = finish_capture(token)
    assert renamed is not None
    assert "user Ada renamed to Ada Lovelace" in renamed
    assert "username changed" in renamed

    token = begin_capture()
    issue_service.update_issue(session, issue.id, description="secret body")
    described = finish_capture(token)
    assert described == "KEEL-1 description changed"
    assert "secret body" not in (described or "")

    token = begin_capture()
    issue_service.update_issue(session, issue.id, definition_of_done="secret bar")
    done_note = finish_capture(token)
    assert done_note == "KEEL-1 definition of done changed"
    assert "secret bar" not in (done_note or "")

    token = begin_capture()
    issue_service.update_issue(session, issue.id, title="x" * 400)
    long_note = finish_capture(token)
    assert long_note is not None
    assert long_note.endswith("…")
    assert len(long_note) <= 300

    series = Series(
        project_id=project.id,
        title="Standup",
        type=IssueType.STORY,
        spawn_mode=SeriesSpawnMode.CALENDAR,
        sprint_basis=SeriesSprintBasis.DUE_ON,
        freq=RecurrenceFreq.DAILY,
        starts_on=date(2026, 10, 14),
    )
    session.add(series)
    session.flush()
    token = begin_capture()
    session.add(SeriesSkip(series_id=series.id, occurrence_on=date(2026, 10, 15)))
    session.add(SeriesLabel(series_id=series.id, label_id=label.id))
    session.flush()
    series_note = finish_capture(token)
    assert series_note is not None
    assert "series Standup skip 2026-10-15" in series_note
    assert "series Standup labels changed" in series_note

    token = begin_capture()
    session.delete(access)
    session.flush()
    assert finish_capture(token) == "API token laptop revoked"

    comment = session.scalars(select(Comment)).one()
    comment.author_id = None
    session.flush()
    token = begin_capture()
    session.delete(user)
    session.flush()
    assert finish_capture(token) == "user Ada Lovelace deleted"


def test_size_limit_drops_the_oldest_rows(session: Session) -> None:
    for number in range(5):
        session.add(
            RequestLog(
                actor_name="Ada",
                method="GET",
                path=f"/item/{number}",
                status_code=200,
            ),
        )
    session.flush()
    enforce_retention(
        session,
        KeelSettings(
            _env_file=None,
            request_log_max_age_days=0,
            request_log_max_bytes=80,
        ),
    )
    session.flush()
    remaining = session.scalars(
        select(RequestLog).order_by(RequestLog.id),
    ).all()
    assert stored_bytes(session) <= 80
    assert [row.path for row in remaining] == ["/item/4"]
