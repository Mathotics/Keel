"""Personal reminder rules and per-issue snooze or dismiss state."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now


class ReminderRule(Base):
    """One person's default, series rule, or issue rule.

    An empty rule still blocks inheritance.
    """

    __tablename__ = "reminder_rules"
    __table_args__ = (
        CheckConstraint(
            "scope in ('default', 'series', 'issue')",
            name="ck_reminder_rules_scope",
        ),
        CheckConstraint(
            "(scope = 'default' and series_id is null and issue_id is null) "
            "or (scope = 'series' and series_id is not null and issue_id is null) "
            "or (scope = 'issue' and issue_id is not null and series_id is null)",
            name="ck_reminder_rules_target",
        ),
        Index(
            "uq_reminder_rules_default",
            "user_id",
            unique=True,
            sqlite_where=text("scope = 'default'"),
        ),
        Index(
            "uq_reminder_rules_series",
            "user_id",
            "series_id",
            unique=True,
            sqlite_where=text("scope = 'series'"),
        ),
        Index(
            "uq_reminder_rules_issue",
            "user_id",
            "issue_id",
            unique=True,
            sqlite_where=text("scope = 'issue'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(16))
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"),
        default=None,
    )
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        default=None,
    )
    start_offsets: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    at_start: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    due_offsets: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    at_due: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    overdue: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReminderIssueState(Base):
    """Snooze and dismiss for one person and one issue. The series rule stays put."""

    __tablename__ = "reminder_issue_states"
    __table_args__ = (
        Index(
            "uq_reminder_issue_states_user_issue",
            "user_id",
            "issue_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    overdue_dismissed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
