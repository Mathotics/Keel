from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now
from keel.domain.enums import NotificationType

_TYPE_VALUES = ", ".join(repr(item.value) for item in NotificationType)
_TYPE_CHECK = f"type in ({_TYPE_VALUES})"


class Notice(Base):
    """One inbox row for one person. The issue key and title survive deletion."""

    __tablename__ = "notices"
    __table_args__ = (
        Index("ix_notices_recipient_created", "recipient_id", "created_at"),
        Index("ix_notices_deliver_at", "deliver_at"),
        CheckConstraint(_TYPE_CHECK, name="ck_notices_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    notice_type: Mapped[str] = mapped_column("type", String(32))
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    actor_name: Mapped[str] = mapped_column(String(100))
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL"),
        default=None,
    )
    issue_key: Mapped[str] = mapped_column(String(32))
    issue_title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    phone: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    bell: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    deliver_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    phone_sent_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class NotificationPreference(Base):
    """A stored override. A missing row means bell on, email off, phone off."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "type",
            name="uq_notification_preferences_user_type",
        ),
        CheckConstraint(_TYPE_CHECK, name="ck_notification_preferences_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    notice_type: Mapped[str] = mapped_column("type", String(32))
    email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    phone: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    bell: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
