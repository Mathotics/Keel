from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class IssueLabel(Base):
    __tablename__ = "issue_labels"
    __table_args__ = (Index("ix_issue_labels_label_id", "label_id"),)

    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"),
        primary_key=True,
    )
