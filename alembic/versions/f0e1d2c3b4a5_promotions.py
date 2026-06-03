"""promotions

Revision ID: f0e1d2c3b4a5
Revises: e0f1a2b3c4d5
Create Date: 2026-06-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f0e1d2c3b4a5"
down_revision: str | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promotions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sanatorium_id", sa.Uuid(), nullable=False),
        sa.Column("name", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "mobile_rate",
                "basic_deal",
                "early_bird",
                "last_minute",
                "long_stay",
                "seasonal",
                "member",
                "package",
                "custom",
                name="promotioncategory",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "paused",
                "inactive",
                name="promotionstatus",
                native_enum=False,
                length=20,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("booking_date_from", sa.Date(), nullable=True),
        sa.Column("booking_date_to", sa.Date(), nullable=True),
        sa.Column("stay_date_from", sa.Date(), nullable=True),
        sa.Column("stay_date_to", sa.Date(), nullable=True),
        sa.Column(
            "booking_weekdays",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "stay_weekdays",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("booking_time_from", sa.Time(), nullable=True),
        sa.Column("booking_time_to", sa.Time(), nullable=True),
        sa.Column(
            "audience",
            sa.Enum(
                "all_guests",
                name="promotionaudience",
                native_enum=False,
                length=30,
            ),
            server_default="all_guests",
            nullable=False,
        ),
        sa.Column(
            "cancellation_policy_mode",
            sa.Enum(
                "original",
                "custom",
                name="promotioncancellationpolicymode",
                native_enum=False,
                length=20,
            ),
            server_default="original",
            nullable=False,
        ),
        sa.Column(
            "custom_cancellation_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "pay_with_cost_per_sale_account",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sanatorium_id"], ["sanatoriums.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_promotions_booking_date_from", "promotions", ["booking_date_from"]
    )
    op.create_index("ix_promotions_booking_date_to", "promotions", ["booking_date_to"])
    op.create_index("ix_promotions_category", "promotions", ["category"])
    op.create_index("ix_promotions_sanatorium_id", "promotions", ["sanatorium_id"])
    op.create_index("ix_promotions_status", "promotions", ["status"])
    op.create_index("ix_promotions_stay_date_from", "promotions", ["stay_date_from"])
    op.create_index("ix_promotions_stay_date_to", "promotions", ["stay_date_to"])

    op.create_table(
        "promotion_rate_plans",
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("rate_plan_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["promotion_id"], ["promotions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rate_plan_id"], ["rate_plans.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("promotion_id", "rate_plan_id"),
    )


def downgrade() -> None:
    op.drop_table("promotion_rate_plans")
    op.drop_index("ix_promotions_stay_date_to", table_name="promotions")
    op.drop_index("ix_promotions_stay_date_from", table_name="promotions")
    op.drop_index("ix_promotions_status", table_name="promotions")
    op.drop_index("ix_promotions_sanatorium_id", table_name="promotions")
    op.drop_index("ix_promotions_category", table_name="promotions")
    op.drop_index("ix_promotions_booking_date_to", table_name="promotions")
    op.drop_index("ix_promotions_booking_date_from", table_name="promotions")
    op.drop_table("promotions")
