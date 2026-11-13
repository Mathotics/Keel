"""Channels and quiet-period clock on a notice.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notices",
        sa.Column("email", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "notices",
        sa.Column("phone", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "notices",
        sa.Column("bell", sa.Boolean(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "notices",
        sa.Column(
            "changed_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "notices",
        sa.Column("phone_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notices", "phone_sent_at")
    op.drop_column("notices", "changed_at")
    op.drop_column("notices", "bell")
    op.drop_column("notices", "phone")
    op.drop_column("notices", "email")
