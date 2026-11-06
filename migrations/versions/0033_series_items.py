"""Schedule trees: child recipes under a series root.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "series_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("parent_item_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column(
            "priority", sa.String(length=20), server_default="p4", nullable=False
        ),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("start_offset_days", sa.Integer(), nullable=True),
        sa.Column("start_minute_of_day", sa.Integer(), nullable=True),
        sa.Column("due_offset_days", sa.Integer(), nullable=True),
        sa.Column("due_minute_of_day", sa.Integer(), nullable=True),
        sa.Column("removed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_series_items_position"),
        sa.CheckConstraint(
            "(start_offset_days is null and start_minute_of_day is null) "
            "or (start_offset_days is not null and start_minute_of_day is not null "
            "and start_offset_days >= 0 "
            "and start_minute_of_day >= 0 and start_minute_of_day < 1440)",
            name="ck_series_items_start_minute_of_day",
        ),
        sa.CheckConstraint(
            "(due_offset_days is null and due_minute_of_day is null) "
            "or (due_offset_days is not null and due_minute_of_day is not null "
            "and due_offset_days >= 0 "
            "and due_minute_of_day >= 0 and due_minute_of_day < 1440)",
            name="ck_series_items_due_minute_of_day",
        ),
        sa.CheckConstraint(
            "start_offset_days is null or due_offset_days is null or ("
            "(-start_offset_days * 1440 + start_minute_of_day) "
            "<= (due_offset_days * 1440 + due_minute_of_day))",
            name="ck_series_items_start_not_after_due",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_item_id"],
            ["series_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_series_items_series_id", "series_items", ["series_id"])
    op.create_index(
        "ix_series_items_parent_item_id",
        "series_items",
        ["parent_item_id"],
    )
    op.create_table(
        "series_item_labels",
        sa.Column("series_item_id", sa.Integer(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["labels.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["series_item_id"],
            ["series_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("series_item_id", "label_id"),
    )
    op.create_index(
        "ix_series_item_labels_label_id",
        "series_item_labels",
        ["label_id"],
    )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("series_item_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_issues_series_item_id",
            "series_items",
            ["series_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_issues_series_item_id", ["series_item_id"])
    op.drop_index("uq_issues_series_occurrence", table_name="issues")
    op.create_index(
        "uq_issues_series_root_occurrence",
        "issues",
        ["series_id", "occurrence_on"],
        unique=True,
        sqlite_where=sa.text("series_id is not null and series_item_id is null"),
    )
    op.create_index(
        "uq_issues_series_item_occurrence",
        "issues",
        ["series_item_id", "occurrence_on"],
        unique=True,
        sqlite_where=sa.text("series_item_id is not null"),
    )


def downgrade() -> None:
    op.drop_index("uq_issues_series_item_occurrence", table_name="issues")
    op.drop_index("uq_issues_series_root_occurrence", table_name="issues")
    op.create_index(
        "uq_issues_series_occurrence",
        "issues",
        ["series_id", "occurrence_on"],
        unique=True,
        sqlite_where=sa.text("series_id is not null"),
    )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_index("ix_issues_series_item_id")
        batch_op.drop_constraint("fk_issues_series_item_id", type_="foreignkey")
        batch_op.drop_column("series_item_id")
    op.drop_index("ix_series_item_labels_label_id", table_name="series_item_labels")
    op.drop_table("series_item_labels")
    op.drop_index("ix_series_items_parent_item_id", table_name="series_items")
    op.drop_index("ix_series_items_series_id", table_name="series_items")
    op.drop_table("series_items")
