"""Add due_at to issues

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("due_at")
