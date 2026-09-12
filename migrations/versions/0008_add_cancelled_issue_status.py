"""Allow cancelled as an issue status

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("todo", "in_progress", "in_review", "blocked", "done")
NEW = (*OLD, "cancelled")


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*OLD, name="ck_issues_status", native_enum=False),
            type_=sa.Enum(*NEW, name="ck_issues_status", native_enum=False),
            existing_nullable=False,
            existing_server_default="todo",
        )


def downgrade() -> None:
    op.execute(sa.text("UPDATE issues SET status = 'todo' WHERE status = 'cancelled'"))
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*NEW, name="ck_issues_status", native_enum=False),
            type_=sa.Enum(*OLD, name="ck_issues_status", native_enum=False),
            existing_nullable=False,
            existing_server_default="todo",
        )
