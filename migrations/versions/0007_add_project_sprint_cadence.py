"""Add auto-sprint cadence to projects

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CADENCES = ("off", "weekly", "two_weeks", "monthly", "every_n_days")


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "sprint_cadence",
                sa.Enum(
                    *CADENCES,
                    name="ck_projects_sprint_cadence",
                    native_enum=False,
                ),
                server_default="off",
                nullable=False,
            ),
        )
        batch_op.add_column(
            sa.Column("sprint_cadence_days", sa.Integer(), nullable=True),
        )
        batch_op.add_column(
            sa.Column(
                "auto_sprint_notice",
                sa.Text(),
                server_default="",
                nullable=False,
            ),
        )
        batch_op.create_check_constraint(
            "ck_projects_sprint_cadence_days_positive",
            "sprint_cadence_days is null or sprint_cadence_days >= 1",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_projects_sprint_cadence_days_positive",
            type_="check",
        )
        batch_op.drop_column("auto_sprint_notice")
        batch_op.drop_column("sprint_cadence_days")
        batch_op.drop_column("sprint_cadence")
