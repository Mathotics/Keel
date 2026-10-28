"""Add issue definition_of_done and allow it on issue_history.field

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
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
)
NEW_FIELDS = (*OLD_FIELDS, "definition of done")


def _in_list(fields: tuple[str, ...]) -> str:
    return "field in (" + ", ".join(f"'{name}'" for name in fields) + ")"


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "definition_of_done",
                sa.Text(),
                server_default="",
                nullable=False,
            ),
        )
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(NEW_FIELDS),
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM issue_history WHERE field = 'definition of done'"),
    )
    with op.batch_alter_table("issue_history") as batch_op:
        batch_op.drop_constraint("ck_issue_history_field", type_="check")
        batch_op.create_check_constraint(
            "ck_issue_history_field",
            _in_list(OLD_FIELDS),
        )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("definition_of_done")
