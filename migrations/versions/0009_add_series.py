"""Add repeating series and occurrence links

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES = ("epic", "story", "subtask")
STATES = ("active", "paused", "stopped")
SPAWN = ("calendar", "after_closed")
BASIS = ("due_on", "created_on")
FREQS = ("daily", "weekly", "monthly", "yearly")


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "type",
            sa.Enum(*TYPES, name="ck_series_type", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(*STATES, name="ck_series_state", native_enum=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "spawn_mode",
            sa.Enum(*SPAWN, name="ck_series_spawn_mode", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "sprint_basis",
            sa.Enum(*BASIS, name="ck_series_sprint_basis", native_enum=False),
            nullable=False,
        ),
        sa.Column("look_ahead_n", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "freq",
            sa.Enum(*FREQS, name="ck_series_freq", native_enum=False),
            nullable=False,
        ),
        sa.Column("interval", sa.Integer(), server_default="1", nullable=False),
        sa.Column("weekdays", sa.String(length=20), server_default="", nullable=False),
        sa.Column("month_day", sa.Integer(), nullable=True),
        sa.Column("nth_week", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=True),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("issues.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reporter_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("interval >= 1", name="ck_series_interval_positive"),
        sa.CheckConstraint("look_ahead_n >= 1", name="ck_series_look_ahead_positive"),
        sa.CheckConstraint(
            "occurrence_count is null or occurrence_count >= 1",
            name="ck_series_count_positive",
        ),
    )
    op.create_index("ix_series_project_id", "series", ["project_id"])
    op.create_table(
        "series_skips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "series_id",
            "occurrence_on",
            name="uq_series_skips_occurrence",
        ),
    )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("series_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("occurrence_on", sa.Date(), nullable=True))
        batch_op.create_foreign_key(
            "fk_issues_series_id",
            "series",
            ["series_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_issues_series_id", ["series_id"])
    op.create_index(
        "uq_issues_series_occurrence",
        "issues",
        ["series_id", "occurrence_on"],
        unique=True,
        sqlite_where=sa.text("series_id is not null"),
    )


def downgrade() -> None:
    op.drop_index("uq_issues_series_occurrence", table_name="issues")
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_index("ix_issues_series_id")
        batch_op.drop_constraint("fk_issues_series_id", type_="foreignkey")
        batch_op.drop_column("occurrence_on")
        batch_op.drop_column("series_id")
    op.drop_table("series_skips")
    op.drop_index("ix_series_project_id", table_name="series")
    op.drop_table("series")
