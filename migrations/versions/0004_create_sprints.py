"""Create sprints and attach issues to them

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPRINT_STATES = ("planned", "active", "completed")


def upgrade() -> None:
    op.create_table(
        "sprints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("goal", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "state",
            sa.Enum(*SPRINT_STATES, name="ck_sprints_state", native_enum=False),
            server_default="planned",
            nullable=False,
        ),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "ends_on is null or starts_on is null or ends_on >= starts_on",
            name="ck_sprints_ends_not_before_starts",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sprints_project_id", "sprints", ["project_id"], unique=False)
    op.create_index(
        "uq_sprints_one_active",
        "sprints",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("state = 'active'"),
    )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sprint_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_issues_sprint_id",
            "sprints",
            ["sprint_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_issues_sprint_id", ["sprint_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_index("ix_issues_sprint_id")
        batch_op.drop_constraint("fk_issues_sprint_id", type_="foreignkey")
        batch_op.drop_column("sprint_id")

    op.drop_index("uq_sprints_one_active", table_name="sprints")
    op.drop_index("ix_sprints_project_id", table_name="sprints")
    op.drop_table("sprints")
