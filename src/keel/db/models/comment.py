from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_issue_created", "issue_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        default=None,
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
