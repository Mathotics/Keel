"""Roles, permissions, and the day-one grants

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint(
            "scope in ('global', 'project')",
            name="ck_permissions_scope",
        ),
    )
    op.create_table(
        "permission_dependencies",
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("requires_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requires_id"],
            ["permissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("permission_id", "requires_id"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("bypass", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint("scope in ('global', 'project')", name="ck_roles_scope"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_user_roles_global",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        sqlite_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_user_roles_project",
        "user_roles",
        ["user_id", "project_id"],
        unique=True,
        sqlite_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_user_permissions_global",
        "user_permissions",
        ["user_id", "permission_id"],
        unique=True,
        sqlite_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_user_permissions_project",
        "user_permissions",
        ["user_id", "permission_id", "project_id"],
        unique=True,
        sqlite_where=sa.text("project_id IS NOT NULL"),
    )
    from keel.services.access import assign_day_one

    session = Session(bind=op.get_bind())
    assign_day_one(session)
    session.flush()


def downgrade() -> None:
    op.drop_index("uq_user_permissions_project", table_name="user_permissions")
    op.drop_index("uq_user_permissions_global", table_name="user_permissions")
    op.drop_table("user_permissions")
    op.drop_index("uq_user_roles_project", table_name="user_roles")
    op.drop_index("uq_user_roles_global", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permission_dependencies")
    op.drop_table("permissions")
