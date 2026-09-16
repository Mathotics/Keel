"""Add priority to issues

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIORITIES = ("p1", "p2", "p3", "p4", "p5")


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "priority",
                sa.Enum(*PRIORITIES, name="ck_issues_priority", native_enum=False),
                nullable=False,
                server_default="p3",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("priority")
