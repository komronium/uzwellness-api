"""admin reservation management

Revision ID: d9e4c7a1b2f3
Revises: b4c8e7d2a9f1
Create Date: 2026-06-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9e4c7a1b2f3"
down_revision: str | None = "b4c8e7d2a9f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("reservation_number", sa.String(length=24), nullable=True),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn
            FROM bookings
        )
        UPDATE bookings AS b
        SET reservation_number = (9000000000000000 + numbered.rn)::text
        FROM numbered
        WHERE b.id = numbered.id
        """
    )
    op.alter_column("bookings", "reservation_number", nullable=False)
    op.create_index(
        "ix_bookings_reservation_number",
        "bookings",
        ["reservation_number"],
        unique=True,
    )
    op.add_column("bookings", sa.Column("special_requests", sa.String(1000)))
    op.add_column(
        "bookings",
        sa.Column("confirmation", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("rate_plan_name", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.add_column("bookings", sa.Column("board_guests", sa.Integer()))
    op.add_column(
        "bookings",
        sa.Column(
            "is_processed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index("ix_bookings_is_processed", "bookings", ["is_processed"])
    op.add_column(
        "bookings",
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.add_column("bookings", sa.Column("processed_by_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_bookings_processed_by_id_users",
        "bookings",
        "users",
        ["processed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_bookings_processed_by_id", "bookings", ["processed_by_id"])

    op.add_column(
        "sanatoriums",
        sa.Column(
            "reservation_auto_confirmation_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "sanatoriums",
        sa.Column(
            "reservation_fallback_processing_method",
            sa.String(length=20),
            server_default="email",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatoriums",
        sa.Column("reservation_fallback_contact_name", sa.String(length=120)),
    )
    op.add_column(
        "sanatoriums",
        sa.Column("reservation_fallback_contact", sa.String(length=255)),
    )

    op.create_table(
        "rate_plan_date_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rate_plan_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("selling_rate", sa.Numeric(12, 2)),
        sa.Column("is_closed", sa.Boolean()),
        sa.Column("min_advance_hours", sa.Integer()),
        sa.Column("max_advance_hours", sa.Integer()),
        sa.Column("min_stay_nights", sa.Integer()),
        sa.Column("min_stay_arrival_nights", sa.Integer()),
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
            ["rate_plan_id"], ["rate_plans.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rate_plan_id", "date", name="uq_rate_plan_date_rule"),
    )
    op.create_index(
        "ix_rate_plan_date_rules_rate_plan_id",
        "rate_plan_date_rules",
        ["rate_plan_id"],
    )
    op.create_index(
        "ix_rate_plan_date_rules_date",
        "rate_plan_date_rules",
        ["date"],
    )


def downgrade() -> None:
    op.drop_index("ix_rate_plan_date_rules_date", table_name="rate_plan_date_rules")
    op.drop_index(
        "ix_rate_plan_date_rules_rate_plan_id",
        table_name="rate_plan_date_rules",
    )
    op.drop_table("rate_plan_date_rules")

    op.drop_column("sanatoriums", "reservation_fallback_contact")
    op.drop_column("sanatoriums", "reservation_fallback_contact_name")
    op.drop_column("sanatoriums", "reservation_fallback_processing_method")
    op.drop_column("sanatoriums", "reservation_auto_confirmation_enabled")

    op.drop_index("ix_bookings_processed_by_id", table_name="bookings")
    op.drop_constraint(
        "fk_bookings_processed_by_id_users", "bookings", type_="foreignkey"
    )
    op.drop_column("bookings", "processed_by_id")
    op.drop_column("bookings", "processed_at")
    op.drop_index("ix_bookings_is_processed", table_name="bookings")
    op.drop_column("bookings", "is_processed")
    op.drop_column("bookings", "board_guests")
    op.drop_column("bookings", "rate_plan_name")
    op.drop_column("bookings", "confirmation")
    op.drop_column("bookings", "special_requests")
    op.drop_index("ix_bookings_reservation_number", table_name="bookings")
    op.drop_column("bookings", "reservation_number")
