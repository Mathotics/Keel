"""Add time spent on issues and its history name.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_FIELDS = (
    "status",
    "assignee",
    "sprint",
    "estimate",
    "remaining",
    "due date",
    "parent",
    "type",
    "title",
    "description",
    "priority",
    "labels",
    "definition of done",
    "location",
    "planned value",
    "earned value",
    "actual cost",
)
NEW_FIELDS = (
    "status",
    "assignee",
    "sprint",
    "estimate",
    "remaining",
    "time spent",
    "due date",
    "parent",
    "type",
    "title",
    "description",
    "priority",
    "labels",
    "definition of done",
    "location",
    "planned value",
    "earned value",
    "actual cost",
)


def _in_list(fields: tuple[str, ...]) -> str:
    return "field in (" + ", ".join(f"'{name}'" for name in fields) + ")"


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.add_column(sa.Column("spent_minutes", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_issues_spent_not_negative",
            "spent_minutes is null or spent_minutes >= 0",
        )
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(NEW_FIELDS),
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM issue_history WHERE field = 'time spent'"))
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(OLD_FIELDS),
        )
    with op.batch_alter_table("issues") as batch_op:
        batch_op.drop_constraint("ck_issues_spent_not_negative", type_="check")
        batch_op.drop_column("spent_minutes")
