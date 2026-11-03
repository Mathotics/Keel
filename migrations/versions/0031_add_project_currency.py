"""Add a project currency, defaulting existing projects to USD.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "currency",
                sa.String(length=3),
                server_default="USD",
                nullable=False,
            ),
        )
        batch_op.create_check_constraint(
            "ck_projects_currency_code",
            "currency GLOB '[A-Z][A-Z][A-Z]'",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint("ck_projects_currency_code", type_="check")
        batch_op.drop_column("currency")
