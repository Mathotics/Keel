"""Make series start and due offsets optional

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_START = "start_minute_of_day >= 0 and start_minute_of_day < 1440"
OLD_DUE = "due_minute_of_day >= 0 and due_minute_of_day < 1440"
OLD_WINDOW = (
    "(-start_offset_days * 1440 + start_minute_of_day) "
    "<= (due_offset_days * 1440 + due_minute_of_day)"
)
NEW_START = (
    "(start_offset_days is null and start_minute_of_day is null) "
    "or (start_offset_days is not null and start_minute_of_day is not null "
    "and start_offset_days >= 0 "
    "and start_minute_of_day >= 0 and start_minute_of_day < 1440)"
)
NEW_DUE = (
    "(due_offset_days is null and due_minute_of_day is null) "
    "or (due_offset_days is not null and due_minute_of_day is not null "
    "and due_offset_days >= 0 "
    "and due_minute_of_day >= 0 and due_minute_of_day < 1440)"
)
NEW_WINDOW = (
    "start_offset_days is null or due_offset_days is null or ("
    "(-start_offset_days * 1440 + start_minute_of_day) "
    "<= (due_offset_days * 1440 + due_minute_of_day))"
)


def upgrade() -> None:
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_constraint("ck_series_start_minute_of_day", type_="check")
        batch_op.drop_constraint("ck_series_due_minute_of_day", type_="check")
        batch_op.drop_constraint("ck_series_start_not_after_due", type_="check")
        for name in (
            "start_offset_days",
            "start_minute_of_day",
            "due_offset_days",
            "due_minute_of_day",
        ):
            batch_op.alter_column(
                name,
                existing_type=sa.Integer(),
                existing_nullable=False,
                existing_server_default="0",
                nullable=True,
                server_default=None,
            )
        batch_op.create_check_constraint("ck_series_start_minute_of_day", NEW_START)
        batch_op.create_check_constraint("ck_series_due_minute_of_day", NEW_DUE)
        batch_op.create_check_constraint("ck_series_start_not_after_due", NEW_WINDOW)


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE series SET "
            "start_offset_days = COALESCE(start_offset_days, 0), "
            "start_minute_of_day = COALESCE(start_minute_of_day, 0), "
            "due_offset_days = COALESCE(due_offset_days, 0), "
            "due_minute_of_day = COALESCE(due_minute_of_day, 0)"
        ),
    )
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_constraint("ck_series_start_minute_of_day", type_="check")
        batch_op.drop_constraint("ck_series_due_minute_of_day", type_="check")
        batch_op.drop_constraint("ck_series_start_not_after_due", type_="check")
        for name in (
            "start_offset_days",
            "start_minute_of_day",
            "due_offset_days",
            "due_minute_of_day",
        ):
            batch_op.alter_column(
                name,
                existing_type=sa.Integer(),
                existing_nullable=True,
                nullable=False,
                server_default="0",
            )
        batch_op.create_check_constraint("ck_series_start_minute_of_day", OLD_START)
        batch_op.create_check_constraint("ck_series_due_minute_of_day", OLD_DUE)
        batch_op.create_check_constraint("ck_series_start_not_after_due", OLD_WINDOW)
