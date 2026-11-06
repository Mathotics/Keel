from datetime import date, datetime

from sqlalchemy import (
    Boolean,
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

from keel.db.base import Base
from keel.db.models.user import utc_now
from keel.domain.enums import (
    INITIAL_PRIORITY,
    IssuePriority,
    IssueType,
    RecurrenceFreq,
    SeriesSpawnMode,
    SeriesSprintBasis,
    SeriesState,
)

SeriesEnum = (
    type[IssueType]
    | type[IssuePriority]
    | type[SeriesState]
    | type[SeriesSpawnMode]
    | type[SeriesSprintBasis]
    | type[RecurrenceFreq]
)


def _enum_column(enum: SeriesEnum, name: str) -> Enum:
    return Enum(
        enum,
        native_enum=False,
        validate_strings=True,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (
        CheckConstraint(
            "interval >= 1",
            name="ck_series_interval_positive",
        ),
        CheckConstraint(
            "look_ahead_n >= 1",
            name="ck_series_look_ahead_positive",
        ),
        CheckConstraint(
            "occurrence_count is null or occurrence_count >= 1",
            name="ck_series_count_positive",
        ),
        CheckConstraint(
            "(start_offset_days is null and start_minute_of_day is null) "
            "or (start_offset_days is not null and start_minute_of_day is not null "
            "and start_offset_days >= 0 "
            "and start_minute_of_day >= 0 and start_minute_of_day < 1440)",
            name="ck_series_start_minute_of_day",
        ),
        CheckConstraint(
            "(due_offset_days is null and due_minute_of_day is null) "
            "or (due_offset_days is not null and due_minute_of_day is not null "
            "and due_offset_days >= 0 "
            "and due_minute_of_day >= 0 and due_minute_of_day < 1440)",
            name="ck_series_due_minute_of_day",
        ),
        CheckConstraint(
            "start_offset_days is null or due_offset_days is null or ("
            "(-start_offset_days * 1440 + start_minute_of_day) "
            "<= (due_offset_days * 1440 + due_minute_of_day))",
            name="ck_series_start_not_after_due",
        ),
        Index("ix_series_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    type: Mapped[IssueType] = mapped_column(_enum_column(IssueType, "ck_series_type"))
    priority: Mapped[IssuePriority] = mapped_column(
        _enum_column(IssuePriority, "ck_series_priority"),
        default=INITIAL_PRIORITY,
        server_default=INITIAL_PRIORITY.value,
    )
    state: Mapped[SeriesState] = mapped_column(
        _enum_column(SeriesState, "ck_series_state"),
        default=SeriesState.ACTIVE,
        server_default=SeriesState.ACTIVE.value,
    )
    spawn_mode: Mapped[SeriesSpawnMode] = mapped_column(
        _enum_column(SeriesSpawnMode, "ck_series_spawn_mode"),
    )
    sprint_basis: Mapped[SeriesSprintBasis] = mapped_column(
        _enum_column(SeriesSprintBasis, "ck_series_sprint_basis"),
    )
    look_ahead_n: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    start_offset_days: Mapped[int | None] = mapped_column(Integer, default=None)
    start_minute_of_day: Mapped[int | None] = mapped_column(Integer, default=None)
    due_offset_days: Mapped[int | None] = mapped_column(Integer, default=None)
    due_minute_of_day: Mapped[int | None] = mapped_column(Integer, default=None)
    freq: Mapped[RecurrenceFreq] = mapped_column(
        _enum_column(RecurrenceFreq, "ck_series_freq"),
    )
    interval: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    weekdays: Mapped[str] = mapped_column(String(20), default="", server_default="")
    month_day: Mapped[int | None] = mapped_column(Integer, default=None)
    nth_week: Mapped[int | None] = mapped_column(Integer, default=None)
    month: Mapped[int | None] = mapped_column(Integer, default=None)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date, default=None)
    occurrence_count: Mapped[int | None] = mapped_column(Integer, default=None)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL"),
        default=None,
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )


class SeriesSkip(Base):
    __tablename__ = "series_skips"
    __table_args__ = (
        UniqueConstraint(
            "series_id",
            "occurrence_on",
            name="uq_series_skips_occurrence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"),
    )
    occurrence_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SeriesItem(Base):
    """One child recipe on a schedule. The series row itself is the root."""

    __tablename__ = "series_items"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_series_items_position"),
        CheckConstraint(
            "(start_offset_days is null and start_minute_of_day is null) "
            "or (start_offset_days is not null and start_minute_of_day is not null "
            "and start_offset_days >= 0 "
            "and start_minute_of_day >= 0 and start_minute_of_day < 1440)",
            name="ck_series_items_start_minute_of_day",
        ),
        CheckConstraint(
            "(due_offset_days is null and due_minute_of_day is null) "
            "or (due_offset_days is not null and due_minute_of_day is not null "
            "and due_offset_days >= 0 "
            "and due_minute_of_day >= 0 and due_minute_of_day < 1440)",
            name="ck_series_items_due_minute_of_day",
        ),
        CheckConstraint(
            "start_offset_days is null or due_offset_days is null or ("
            "(-start_offset_days * 1440 + start_minute_of_day) "
            "<= (due_offset_days * 1440 + due_minute_of_day))",
            name="ck_series_items_start_not_after_due",
        ),
        Index("ix_series_items_series_id", "series_id"),
        Index("ix_series_items_parent_item_id", "parent_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"),
    )
    parent_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("series_items.id", ondelete="CASCADE"),
        default=None,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    type: Mapped[IssueType] = mapped_column(
        _enum_column(IssueType, "ck_series_items_type"),
    )
    priority: Mapped[IssuePriority] = mapped_column(
        _enum_column(IssuePriority, "ck_series_items_priority"),
        default=INITIAL_PRIORITY,
        server_default=INITIAL_PRIORITY.value,
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    start_offset_days: Mapped[int | None] = mapped_column(Integer, default=None)
    start_minute_of_day: Mapped[int | None] = mapped_column(Integer, default=None)
    due_offset_days: Mapped[int | None] = mapped_column(Integer, default=None)
    due_minute_of_day: Mapped[int | None] = mapped_column(Integer, default=None)
    removed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )
