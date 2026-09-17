"""Create labels and issue_labels; allow labels on issue_history.field

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
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
)
NEW_FIELDS = (*OLD_FIELDS, "labels")


def _in_list(fields: tuple[str, ...]) -> str:
    return "field in (" + ", ".join(f"'{name}'" for name in fields) + ")"


def upgrade() -> None:
    op.create_table(
        "labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "issue_labels",
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["label_id"], ["labels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("issue_id", "label_id"),
    )
    op.create_index("ix_issue_labels_label_id", "issue_labels", ["label_id"])
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
    op.drop_index("ix_issue_labels_label_id", table_name="issue_labels")
    op.drop_table("issue_labels")
    op.drop_table("labels")
