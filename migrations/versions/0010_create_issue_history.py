"""Create issue_history for lightweight per-issue field changes

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIELDS = (
    "status",
    "assignee",
    "sprint",
    "estimate",
    "remaining",
    "due date",
    "parent",
    "type",
)


def upgrade() -> None:
    op.create_table(
        "issue_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("actor_name", sa.String(length=100), nullable=False),
        sa.Column("field", sa.String(length=20), nullable=False),
        sa.Column("from_value", sa.Text(), nullable=False),
        sa.Column("to_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "field in (" + ", ".join(f"'{name}'" for name in FIELDS) + ")",
            name="ck_issue_history_field",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_issue_history_issue_created",
        "issue_history",
        ["issue_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_issue_history_issue_created", table_name="issue_history")
    op.drop_table("issue_history")
