"""Create the request log

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=100), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_request_logs_created_id",
        "request_logs",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_request_logs_user_created",
        "request_logs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_request_logs_user_created", table_name="request_logs")
    op.drop_index("ix_request_logs_created_id", table_name="request_logs")
    op.drop_table("request_logs")
