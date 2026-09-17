"""Add required priority on series recipes

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIORITIES = ("p1", "p2", "p3", "p4", "p5")


def upgrade() -> None:
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "priority",
                sa.Enum(*PRIORITIES, name="ck_series_priority", native_enum=False),
                nullable=False,
                server_default="p3",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_column("priority")
