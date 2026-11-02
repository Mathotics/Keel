"""Remember a create key so a repeated submit returns the same issue.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.add_column(
            sa.Column("client_key", sa.String(length=64), nullable=True),
        )
        batch_op.create_unique_constraint("uq_issues_client_key", ["client_key"])


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.drop_constraint("uq_issues_client_key", type_="unique")
        batch_op.drop_column("client_key")
