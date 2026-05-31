"""package rules, rate plan amenities, drop visa requests

Revision ID: ad7e2c9f4b61
Revises: f6a7b8c9d0e1
Create Date: 2026-05-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ad7e2c9f4b61"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_plan_amenities",
        sa.Column("rate_plan_id", sa.Uuid(), nullable=False),
        sa.Column("amenity_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["amenity_id"], ["amenities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["rate_plan_id"], ["rate_plans.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("rate_plan_id", "amenity_id"),
    )
    op.drop_table("visa_requests")


def downgrade() -> None:
    op.create_table(
        "visa_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("citizenship", sa.String(length=120), nullable=False),
        sa.Column("passport_number", sa.String(length=64), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("arrival_date", sa.Date(), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "tourism",
                "treatment",
                "business",
                "other",
                name="visapurpose",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("passport_scan_url", sa.String(length=500), nullable=True),
        sa.Column("issued_document_url", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "issued",
                "rejected",
                name="visastatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
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
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_visa_requests_booking_id"),
        "visa_requests",
        ["booking_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_visa_requests_status"), "visa_requests", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_visa_requests_user_id"), "visa_requests", ["user_id"], unique=False
    )
    op.drop_table("rate_plan_amenities")
