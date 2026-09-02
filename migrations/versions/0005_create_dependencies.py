"""Create dependencies between issues

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEPENDENCY_KINDS = ("blocks", "relates_to")


def upgrade() -> None:
    op.create_table(
        "dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(*DEPENDENCY_KINDS, name="ck_dependencies_kind", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("source_id != target_id", name="ck_dependencies_not_self"),
        sa.ForeignKeyConstraint(["source_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "target_id",
            "kind",
            name="uq_dependencies_edge",
        ),
    )
    op.create_index(
        "ix_dependencies_target_kind",
        "dependencies",
        ["target_id", "kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dependencies_target_kind", table_name="dependencies")
    op.drop_table("dependencies")
