"""Notification inbox and per-type channel preferences.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = (
    "'comment_on_created', 'comment_on_assigned', 'assigned', "
    "'update_on_created', 'update_on_assigned', "
    "'delete_on_created', 'delete_on_assigned'"
)


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=100), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=True),
        sa.Column("issue_key", sa.String(length=32), nullable=False),
        sa.Column("issue_title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deliver_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(f"type in ({_TYPES})", name="ck_notices_type"),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notices_recipient_created",
        "notices",
        ["recipient_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notices_deliver_at",
        "notices",
        ["deliver_at"],
        unique=False,
    )
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("email", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("phone", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("bell", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            f"type in ({_TYPES})",
            name="ck_notification_preferences_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "type",
            name="uq_notification_preferences_user_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_notices_deliver_at", table_name="notices")
    op.drop_index("ix_notices_recipient_created", table_name="notices")
    op.drop_table("notices")
