"""availability operation logs

Revision ID: e0f1a2b3c4d5
Revises: d9e4c7a1b2f3
Create Date: 2026-06-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e4c7a1b2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "availability_operation_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sanatorium_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("rate_plan_id", sa.Uuid(), nullable=True),
        sa.Column("operated_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "room_status_restrictions",
                "inventory",
                "rate",
                "max_rooms_available",
                "cancellation_policy",
                "bulk_operation",
                name="availabilitylogcategory",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("check_in_from", sa.Date(), nullable=True),
        sa.Column("check_in_to", sa.Date(), nullable=True),
        sa.Column(
            "weekdays",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["operated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["rate_plan_id"], ["rate_plans.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["sanatorium_id"], ["sanatoriums.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_operation_logs_action",
        "availability_operation_logs",
        ["action"],
    )
    op.create_index(
        "ix_availability_operation_logs_category",
        "availability_operation_logs",
        ["category"],
    )
    op.create_index(
        "ix_availability_operation_logs_check_in_from",
        "availability_operation_logs",
        ["check_in_from"],
    )
    op.create_index(
        "ix_availability_operation_logs_check_in_to",
        "availability_operation_logs",
        ["check_in_to"],
    )
    op.create_index(
        "ix_availability_operation_logs_created_at",
        "availability_operation_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_availability_operation_logs_operated_by_id",
        "availability_operation_logs",
        ["operated_by_id"],
    )
    op.create_index(
        "ix_availability_operation_logs_rate_plan_id",
        "availability_operation_logs",
        ["rate_plan_id"],
    )
    op.create_index(
        "ix_availability_operation_logs_room_id",
        "availability_operation_logs",
        ["room_id"],
    )
    op.create_index(
        "ix_availability_operation_logs_sanatorium_id",
        "availability_operation_logs",
        ["sanatorium_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_availability_operation_logs_sanatorium_id",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_room_id",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_rate_plan_id",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_operated_by_id",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_created_at",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_check_in_to",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_check_in_from",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_category",
        table_name="availability_operation_logs",
    )
    op.drop_index(
        "ix_availability_operation_logs_action",
        table_name="availability_operation_logs",
    )
    op.drop_table("availability_operation_logs")
