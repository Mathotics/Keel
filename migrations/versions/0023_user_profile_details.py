"""Add optional profile contact fields

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=254), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column(
            "first_name",
            sa.String(length=100),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_name",
            sa.String(length=100),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("date_of_birth")
        batch.drop_column("last_name")
        batch.drop_column("first_name")
        batch.drop_column("email")
