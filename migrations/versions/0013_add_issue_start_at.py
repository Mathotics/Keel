"""Add issue start_at and series start/due offsets

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_BASIS = ("due_on", "created_on")
NEW_BASIS = ("due_on", "start_on", "created_on")


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("start_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            "ck_issues_start_not_after_due",
            "start_at is null or due_at is null or start_at <= due_at",
        )
    op.execute(
        sa.text(
            "UPDATE issues SET start_at = due_at "
            "WHERE series_id is not null AND due_at is not null"
        )
    )
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "start_offset_days",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "start_minute_of_day",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "due_offset_days",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "due_minute_of_day",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
        batch_op.create_check_constraint(
            "ck_series_start_minute_of_day",
            "start_minute_of_day >= 0 and start_minute_of_day < 1440",
        )
        batch_op.create_check_constraint(
            "ck_series_due_minute_of_day",
            "due_minute_of_day >= 0 and due_minute_of_day < 1440",
        )
        batch_op.create_check_constraint(
            "ck_series_start_not_after_due",
            "(start_offset_days * 1440 + start_minute_of_day) "
            "<= (due_offset_days * 1440 + due_minute_of_day)",
        )
        batch_op.alter_column(
            "sprint_basis",
            existing_type=sa.Enum(
                *OLD_BASIS,
                name="ck_series_sprint_basis",
                native_enum=False,
            ),
            type_=sa.Enum(*NEW_BASIS, name="ck_series_sprint_basis", native_enum=False),
            existing_nullable=False,
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE series SET sprint_basis = 'due_on' WHERE sprint_basis = 'start_on'"
        )
    )
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.alter_column(
            "sprint_basis",
            existing_type=sa.Enum(
                *NEW_BASIS,
                name="ck_series_sprint_basis",
                native_enum=False,
            ),
            type_=sa.Enum(*OLD_BASIS, name="ck_series_sprint_basis", native_enum=False),
            existing_nullable=False,
        )
        batch_op.drop_constraint("ck_series_start_not_after_due", type_="check")
        batch_op.drop_constraint("ck_series_due_minute_of_day", type_="check")
        batch_op.drop_constraint("ck_series_start_minute_of_day", type_="check")
        batch_op.drop_column("due_minute_of_day")
        batch_op.drop_column("due_offset_days")
        batch_op.drop_column("start_minute_of_day")
        batch_op.drop_column("start_offset_days")
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_constraint("ck_issues_start_not_after_due", type_="check")
        batch_op.drop_column("start_at")
