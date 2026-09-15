"""Allow title and description on issue_history.field

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
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
)
NEW_FIELDS = (*OLD_FIELDS, "title", "description")


def _in_list(fields: tuple[str, ...]) -> str:
    return "field in (" + ", ".join(f"'{name}'" for name in fields) + ")"


def upgrade() -> None:
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(NEW_FIELDS),
        )


def downgrade() -> None:
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(OLD_FIELDS),
        )
