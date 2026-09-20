"""Store series start offset as days before occurrence

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_WINDOW = (
    "(start_offset_days * 1440 + start_minute_of_day) "
    "<= (due_offset_days * 1440 + due_minute_of_day)"
)
NEW_WINDOW = (
    "(-start_offset_days * 1440 + start_minute_of_day) "
    "<= (due_offset_days * 1440 + due_minute_of_day)"
)


def upgrade() -> None:
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_constraint("ck_series_start_not_after_due", type_="check")
    op.execute(sa.text("UPDATE series SET start_offset_days = -start_offset_days"))
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_series_start_not_after_due",
            NEW_WINDOW,
        )


def downgrade() -> None:
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_constraint("ck_series_start_not_after_due", type_="check")
    op.execute(sa.text("UPDATE series SET start_offset_days = -start_offset_days"))
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_series_start_not_after_due",
            OLD_WINDOW,
        )
