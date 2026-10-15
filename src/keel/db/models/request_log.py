from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now


class RequestLog(Base):
    """One signed-in HTTP request. The path has no query string."""

    __tablename__ = "request_logs"
    __table_args__ = (
        Index("ix_request_logs_created_id", "created_at", "id"),
        Index("ix_request_logs_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    actor_name: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(2048))
    status_code: Mapped[int] = mapped_column(Integer)
    change_note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
