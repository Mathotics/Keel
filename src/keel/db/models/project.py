from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now
from keel.domain.cadence import MAX_SPRINT_AHEAD, MIN_SPRINT_AHEAD
from keel.domain.enums import SprintCadence

KEY_MIN_LENGTH = 2
KEY_MAX_LENGTH = 10


def _cadence_column() -> Enum:
    return Enum(
        SprintCadence,
        native_enum=False,
        validate_strings=True,
        name="ck_projects_sprint_cadence",
        values_callable=lambda members: [member.value for member in members],
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            f"length(key) between {KEY_MIN_LENGTH} and {KEY_MAX_LENGTH}",
            name="ck_projects_key_length",
        ),
        CheckConstraint(
            "sprint_cadence_days is null or sprint_cadence_days >= 1",
            name="ck_projects_sprint_cadence_days_positive",
        ),
        CheckConstraint(
            f"sprint_ahead between {MIN_SPRINT_AHEAD} and {MAX_SPRINT_AHEAD}",
            name="ck_projects_sprint_ahead_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Never decremented, so a deleted issue's number is never handed out again.
    issue_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sprint_cadence: Mapped[SprintCadence] = mapped_column(
        _cadence_column(),
        default=SprintCadence.OFF,
        server_default=SprintCadence.OFF.value,
    )
    sprint_cadence_days: Mapped[int | None] = mapped_column(Integer, default=None)
    sprint_ahead: Mapped[int] = mapped_column(
        Integer,
        default=MIN_SPRINT_AHEAD,
        server_default="0",
    )
    auto_sprint_notice: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
