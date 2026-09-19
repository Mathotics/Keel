"""Add auto-sprint lookahead count to projects

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "sprint_ahead",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
        batch_op.create_check_constraint(
            "ck_projects_sprint_ahead_range",
            "sprint_ahead >= 0 and sprint_ahead <= 12",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_projects_sprint_ahead_range",
            type_="check",
        )
        batch_op.drop_column("sprint_ahead")
