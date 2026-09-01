"""Create the projects, boards, and issues tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ISSUE_TYPES = ("epic", "story", "subtask")
ISSUE_STATUSES = ("todo", "in_progress", "in_review", "blocked", "done")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("issue_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(key) between 2 and 10",
            name="ck_projects_key_length",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(*ISSUE_TYPES, name="ck_issues_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.Enum(*ISSUE_STATUSES, name="ck_issues_status", native_enum=False),
            server_default="todo",
            nullable=False,
        ),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("reporter_id", sa.Integer(), nullable=True),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("estimate_minutes", sa.Integer(), nullable=True),
        sa.Column("remaining_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "estimate_minutes is null or estimate_minutes >= 0",
            name="ck_issues_estimate_not_negative",
        ),
        sa.CheckConstraint(
            "remaining_minutes is null or remaining_minutes >= 0",
            name="ck_issues_remaining_not_negative",
        ),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["issues.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "number", name="uq_issues_project_number"),
    )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.create_index("ix_issues_parent_id", ["parent_id"], unique=False)
        batch_op.create_index(
            "ix_issues_project_created",
            ["project_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_issues_project_status",
            ["project_id", "status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_index("ix_issues_project_status")
        batch_op.drop_index("ix_issues_project_created")
        batch_op.drop_index("ix_issues_parent_id")

    op.drop_table("issues")
    op.drop_table("boards")
    op.drop_table("projects")
