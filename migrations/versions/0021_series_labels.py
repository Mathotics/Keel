"""Link series recipes to the global label catalog

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "series_labels",
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["label_id"], ["labels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "label_id"),
    )
    op.create_index("ix_series_labels_label_id", "series_labels", ["label_id"])


def downgrade() -> None:
    op.drop_index("ix_series_labels_label_id", table_name="series_labels")
    op.drop_table("series_labels")
