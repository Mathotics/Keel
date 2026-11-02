"""Add earned-value cost fields on issues and their history names.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
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
    "definition of done",
    "priority",
    "labels",
)
NEW_FIELDS = (*OLD_FIELDS, "planned value", "earned value", "actual cost")

_COST_COLUMNS = (
    ("planned_value_cents", "ck_issues_planned_value_not_negative"),
    ("earned_value_cents", "ck_issues_earned_value_not_negative"),
    ("actual_cost_cents", "ck_issues_actual_cost_not_negative"),
)


def _in_list(fields: tuple[str, ...]) -> str:
    return "field in (" + ", ".join(f"'{name}'" for name in fields) + ")"


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        for name, constraint in _COST_COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Integer(), nullable=True))
            batch_op.create_check_constraint(
                constraint,
                f"{name} is null or {name} >= 0",
            )
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(NEW_FIELDS),
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM issue_history WHERE field in "
            "('planned value', 'earned value', 'actual cost')",
        ),
    )
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(OLD_FIELDS),
        )
    with op.batch_alter_table("issues") as batch_op:
        for name, constraint in reversed(_COST_COLUMNS):
            batch_op.drop_constraint(constraint, type_="check")
            batch_op.drop_column(name)
