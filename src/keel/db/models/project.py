from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now

KEY_MIN_LENGTH = 2
KEY_MAX_LENGTH = 10


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            f"length(key) between {KEY_MIN_LENGTH} and {KEY_MAX_LENGTH}",
            name="ck_projects_key_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Never decremented, so a deleted issue's number is never handed out again.
    issue_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
