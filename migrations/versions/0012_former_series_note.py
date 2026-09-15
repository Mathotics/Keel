"""Snapshot former series notes on issues; leftover stopped series are retired

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("former_series_title", sa.String(300)))
        batch_op.add_column(sa.Column("former_series_cadence", sa.String(300)))


def downgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("former_series_cadence")
        batch_op.drop_column("former_series_title")
