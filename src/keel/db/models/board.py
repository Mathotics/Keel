from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base


class Board(Base):
    """One row per project. The unique constraint is the one-board rule."""

    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(200))
