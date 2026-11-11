"""Store a phone topic and Firebase device tokens.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phone_topics",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topic", name="uq_phone_topics_topic"),
    )
    op.create_table(
        "phone_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token", name="uq_phone_devices_token"),
    )
    op.create_index("ix_phone_devices_user_id", "phone_devices", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_phone_devices_user_id", table_name="phone_devices")
    op.drop_table("phone_devices")
    op.drop_table("phone_topics")
