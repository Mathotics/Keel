"""Personal reminder rules and per-issue snooze state.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminder_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.Integer(), nullable=True),
        sa.Column("start_offsets", sa.Text(), server_default="[]", nullable=False),
        sa.Column("at_start", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("due_offsets", sa.Text(), server_default="[]", nullable=False),
        sa.Column("at_due", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("overdue", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "scope in ('default', 'series', 'issue')",
            name="ck_reminder_rules_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'default' and series_id is null and issue_id is null) "
            "or (scope = 'series' and series_id is not null and issue_id is null) "
            "or (scope = 'issue' and issue_id is not null and series_id is null)",
            name="ck_reminder_rules_target",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_reminder_rules_default",
        "reminder_rules",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("scope = 'default'"),
    )
    op.create_index(
        "uq_reminder_rules_series",
        "reminder_rules",
        ["user_id", "series_id"],
        unique=True,
        sqlite_where=sa.text("scope = 'series'"),
    )
    op.create_index(
        "uq_reminder_rules_issue",
        "reminder_rules",
        ["user_id", "issue_id"],
        unique=True,
        sqlite_where=sa.text("scope = 'issue'"),
    )
    op.create_table(
        "reminder_issue_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("snooze_until", sa.DateTime(), nullable=True),
        sa.Column(
            "overdue_dismissed", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_reminder_issue_states_user_issue",
        "reminder_issue_states",
        ["user_id", "issue_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reminder_issue_states_user_issue",
        table_name="reminder_issue_states",
    )
    op.drop_table("reminder_issue_states")
    op.drop_index("uq_reminder_rules_issue", table_name="reminder_rules")
    op.drop_index("uq_reminder_rules_series", table_name="reminder_rules")
    op.drop_index("uq_reminder_rules_default", table_name="reminder_rules")
    op.drop_table("reminder_rules")
