from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now


class IssueHistory(Base):
    __tablename__ = "issue_history"
    __table_args__ = (
        CheckConstraint(
            "field in ('status', 'assignee', 'sprint', 'estimate', "
            "'remaining', 'due date', 'parent', 'type', 'title', "
            "'description', 'priority', 'labels')",
            name="ck_issue_history_field",
        ),
        Index("ix_issue_history_issue_created", "issue_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
    )
    actor_name: Mapped[str] = mapped_column(String(100))
    field: Mapped[str] = mapped_column(String(20))
    from_value: Mapped[str] = mapped_column(Text)
    to_value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
