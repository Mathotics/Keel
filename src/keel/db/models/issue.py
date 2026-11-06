from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from keel.db.base import Base
from keel.db.models.user import utc_now
from keel.domain.enums import (
    INITIAL_PRIORITY,
    INITIAL_STATUS,
    IssuePriority,
    IssueStatus,
    IssueType,
)


def _enum_column(
    enum: type[IssueType] | type[IssueStatus] | type[IssuePriority],
    name: str,
) -> Enum:
    """Store the lowercase value, guarded by a CHECK rather than a native type."""
    return Enum(
        enum,
        native_enum=False,
        validate_strings=True,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_issues_project_number"),
        CheckConstraint(
            "estimate_minutes is null or estimate_minutes >= 0",
            name="ck_issues_estimate_not_negative",
        ),
        CheckConstraint(
            "remaining_minutes is null or remaining_minutes >= 0",
            name="ck_issues_remaining_not_negative",
        ),
        CheckConstraint(
            "planned_value_cents is null or planned_value_cents >= 0",
            name="ck_issues_planned_value_not_negative",
        ),
        CheckConstraint(
            "earned_value_cents is null or earned_value_cents >= 0",
            name="ck_issues_earned_value_not_negative",
        ),
        CheckConstraint(
            "actual_cost_cents is null or actual_cost_cents >= 0",
            name="ck_issues_actual_cost_not_negative",
        ),
        CheckConstraint(
            "start_at is null or due_at is null or start_at <= due_at",
            name="ck_issues_start_not_after_due",
        ),
        Index("ix_issues_project_status", "project_id", "status"),
        Index("ix_issues_project_created", "project_id", "created_at"),
        Index("ix_issues_parent_id", "parent_id"),
        Index("ix_issues_sprint_id", "sprint_id"),
        Index("ix_issues_series_id", "series_id"),
        Index("ix_issues_series_item_id", "series_item_id"),
        Index(
            "uq_issues_series_root_occurrence",
            "series_id",
            "occurrence_on",
            unique=True,
            sqlite_where=text("series_id is not null and series_item_id is null"),
        ),
        Index(
            "uq_issues_series_item_occurrence",
            "series_item_id",
            "occurrence_on",
            unique=True,
            sqlite_where=text("series_item_id is not null"),
        ),
        UniqueConstraint("client_key", name="uq_issues_client_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    number: Mapped[int] = mapped_column(Integer)
    type: Mapped[IssueType] = mapped_column(_enum_column(IssueType, "ck_issues_type"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    definition_of_done: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
    )
    location: Mapped[str] = mapped_column(
        String(300),
        default="",
        server_default="",
    )
    status: Mapped[IssueStatus] = mapped_column(
        _enum_column(IssueStatus, "ck_issues_status"),
        default=INITIAL_STATUS,
        server_default=INITIAL_STATUS.value,
    )
    priority: Mapped[IssuePriority] = mapped_column(
        _enum_column(IssuePriority, "ck_issues_priority"),
        default=INITIAL_PRIORITY,
        server_default=INITIAL_PRIORITY.value,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="RESTRICT"),
        default=None,
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.id", ondelete="SET NULL"),
        default=None,
    )
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        default=None,
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        default=None,
    )
    estimate_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    remaining_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    planned_value_cents: Mapped[int | None] = mapped_column(Integer, default=None)
    earned_value_cents: Mapped[int | None] = mapped_column(Integer, default=None)
    actual_cost_cents: Mapped[int | None] = mapped_column(Integer, default=None)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL", use_alter=True),
        default=None,
    )
    occurrence_on: Mapped[date | None] = mapped_column(Date, default=None)
    series_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("series_items.id", ondelete="SET NULL"),
        default=None,
    )
    former_series_title: Mapped[str | None] = mapped_column(String(300), default=None)
    former_series_cadence: Mapped[str | None] = mapped_column(
        String(300),
        default=None,
    )
    client_key: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )
