from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base
from keel.db.models.user import utc_now
from keel.domain.enums import DependencyKind


def _kind_column() -> Enum:
    return Enum(
        DependencyKind,
        native_enum=False,
        validate_strings=True,
        name="ck_dependencies_kind",
        values_callable=lambda members: [member.value for member in members],
    )


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "kind", name="uq_dependencies_edge"),
        CheckConstraint("source_id != target_id", name="ck_dependencies_not_self"),
        Index("ix_dependencies_target_kind", "target_id", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
    )
    kind: Mapped[DependencyKind] = mapped_column(_kind_column())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
