from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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
from keel.domain.enums import INITIAL_STATUS, IssueStatus, IssueType


def _enum_column(enum: type[IssueType] | type[IssueStatus], name: str) -> Enum:
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
        Index("ix_issues_project_status", "project_id", "status"),
        Index("ix_issues_project_created", "project_id", "created_at"),
        Index("ix_issues_parent_id", "parent_id"),
        Index("ix_issues_sprint_id", "sprint_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    number: Mapped[int] = mapped_column(Integer)
    type: Mapped[IssueType] = mapped_column(_enum_column(IssueType, "ck_issues_type"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[IssueStatus] = mapped_column(
        _enum_column(IssueStatus, "ck_issues_status"),
        default=INITIAL_STATUS,
        server_default=INITIAL_STATUS.value,
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
    due_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )
