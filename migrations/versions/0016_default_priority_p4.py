"""Default new issues to P4 without rewriting existing ranks

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
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.alter_column(
            "priority",
            existing_type=sa.Enum(
                *PRIORITIES,
                name="ck_issues_priority",
                native_enum=False,
            ),
            existing_nullable=False,
            existing_server_default="p3",
            server_default="p4",
        )


def downgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.alter_column(
            "priority",
            existing_type=sa.Enum(
                *PRIORITIES,
                name="ck_issues_priority",
                native_enum=False,
            ),
            existing_nullable=False,
            existing_server_default="p4",
            server_default="p3",
        )
