from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now
from keel.domain.enums import SprintState


def _state_column() -> Enum:
    return Enum(
        SprintState,
        native_enum=False,
        validate_strings=True,
        name="ck_sprints_state",
        values_callable=lambda members: [member.value for member in members],
    )


class Sprint(Base):
    __tablename__ = "sprints"
    __table_args__ = (
        CheckConstraint(
            "ends_on is null or starts_on is null or ends_on >= starts_on",
            name="ck_sprints_ends_not_before_starts",
        ),
        Index("ix_sprints_project_id", "project_id"),
        Index(
            "uq_sprints_one_active",
            "project_id",
            unique=True,
            sqlite_where=text("state = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text, default="", server_default="")
    state: Mapped[SprintState] = mapped_column(
        _state_column(),
        default=SprintState.PLANNED,
        server_default=SprintState.PLANNED.value,
    )
    starts_on: Mapped[date | None] = mapped_column(Date, default=None)
    ends_on: Mapped[date | None] = mapped_column(Date, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
