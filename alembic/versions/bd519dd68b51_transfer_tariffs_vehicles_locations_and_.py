"""transfer tariffs, vehicles, locations and transfer_admin role

Revision ID: bd519dd68b51
Revises: 51f31913df6c
Create Date: 2026-07-30 21:39:34.375831

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "bd519dd68b51"
down_revision: Union[str, Sequence[str], None] = "51f31913df6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VEHICLE_TYPE = sa.Enum(
    "sedan", "minivan", "bus", name="vehicletype", native_enum=False, length=20
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "transfer_locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "name",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "airport",
                "city",
                "sanatorium",
                "custom",
                name="transferlocationkind",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transfer_locations_is_active"),
        "transfer_locations",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_locations_kind"), "transfer_locations", ["kind"], unique=False
    )

    op.create_table(
        "transfer_vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_type", _VEHICLE_TYPE, nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("plate", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint(
            "capacity > 0", name="ck_transfer_vehicles_capacity_positive"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transfer_vehicles_is_active"),
        "transfer_vehicles",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_vehicles_plate"), "transfer_vehicles", ["plate"], unique=True
    )
    op.create_index(
        op.f("ix_transfer_vehicles_vehicle_type"),
        "transfer_vehicles",
        ["vehicle_type"],
        unique=False,
    )

    op.create_table(
        "transfer_tariffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("route_from_id", sa.Uuid(), nullable=False),
        sa.Column("route_to_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_type", _VEHICLE_TYPE, nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_transfer_tariffs_period_order",
        ),
        sa.CheckConstraint("price >= 0", name="ck_transfer_tariffs_price_non_negative"),
        sa.CheckConstraint(
            "route_from_id <> route_to_id",
            name="ck_transfer_tariffs_distinct_endpoints",
        ),
        sa.ForeignKeyConstraint(
            ["route_from_id"], ["transfer_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["route_to_id"], ["transfer_locations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transfer_tariffs_route",
        "transfer_tariffs",
        ["route_from_id", "route_to_id"],
        unique=False,
    )
    # Only one open (unclosed) price version per route + vehicle type.
    op.create_index(
        "uq_transfer_tariffs_current",
        "transfer_tariffs",
        ["route_from_id", "route_to_id", "vehicle_type"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )

    op.add_column(
        "transfer_requests", sa.Column("route_from_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "transfer_requests", sa.Column("route_to_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "transfer_requests", sa.Column("vehicle_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "transfer_requests", sa.Column("applied_tariff_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "transfer_requests",
        sa.Column("applied_price", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "transfer_requests",
        sa.Column("applied_currency", sa.String(length=3), nullable=True),
    )
    # Pre-existing rows are manual, off-tariff jobs: unpaid until settled.
    op.add_column(
        "transfer_requests",
        sa.Column(
            "payment_state",
            sa.Enum(
                "included",
                "unpaid",
                "paid",
                name="transferpaymentstate",
                native_enum=False,
                length=20,
            ),
            server_default="unpaid",
            nullable=False,
        ),
    )
    op.add_column(
        "transfer_requests",
        sa.Column(
            "commission_percent_snapshot",
            sa.Numeric(precision=5, scale=2),
            nullable=True,
        ),
    )
    op.add_column(
        "transfer_requests",
        sa.Column(
            "commission_amount_snapshot",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_transfer_requests_applied_price_non_negative",
        "transfer_requests",
        "applied_price IS NULL OR applied_price >= 0",
    )
    op.create_check_constraint(
        "ck_transfer_requests_commission_percent_range",
        "transfer_requests",
        "commission_percent_snapshot IS NULL "
        "OR commission_percent_snapshot BETWEEN 0 AND 100",
    )
    op.create_index(
        op.f("ix_transfer_requests_applied_tariff_id"),
        "transfer_requests",
        ["applied_tariff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_requests_payment_state"),
        "transfer_requests",
        ["payment_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_requests_route_from_id"),
        "transfer_requests",
        ["route_from_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_requests_route_to_id"),
        "transfer_requests",
        ["route_to_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_requests_vehicle_id"),
        "transfer_requests",
        ["vehicle_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_transfer_requests_vehicle_id",
        "transfer_requests",
        "transfer_vehicles",
        ["vehicle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transfer_requests_applied_tariff_id",
        "transfer_requests",
        "transfer_tariffs",
        ["applied_tariff_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transfer_requests_route_from_id",
        "transfer_requests",
        "transfer_locations",
        ["route_from_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transfer_requests_route_to_id",
        "transfer_requests",
        "transfer_locations",
        ["route_to_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "users",
        sa.Column(
            "transfer_commission_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_users_transfer_commission_percent_range",
        "users",
        "transfer_commission_percent IS NULL "
        "OR transfer_commission_percent BETWEEN 0 AND 100",
    )
    # Exactly one transfer operator platform-wide (product decision).
    op.create_index(
        "uq_users_single_transfer_admin",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'transfer_admin'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_users_single_transfer_admin",
        table_name="users",
        postgresql_where=sa.text("role = 'transfer_admin'"),
    )
    op.drop_constraint(
        "ck_users_transfer_commission_percent_range", "users", type_="check"
    )
    op.drop_column("users", "transfer_commission_percent")

    for name in (
        "fk_transfer_requests_route_to_id",
        "fk_transfer_requests_route_from_id",
        "fk_transfer_requests_applied_tariff_id",
        "fk_transfer_requests_vehicle_id",
    ):
        op.drop_constraint(name, "transfer_requests", type_="foreignkey")
    op.drop_constraint(
        "ck_transfer_requests_commission_percent_range",
        "transfer_requests",
        type_="check",
    )
    op.drop_constraint(
        "ck_transfer_requests_applied_price_non_negative",
        "transfer_requests",
        type_="check",
    )
    op.drop_index(
        op.f("ix_transfer_requests_vehicle_id"), table_name="transfer_requests"
    )
    op.drop_index(
        op.f("ix_transfer_requests_route_to_id"), table_name="transfer_requests"
    )
    op.drop_index(
        op.f("ix_transfer_requests_route_from_id"), table_name="transfer_requests"
    )
    op.drop_index(
        op.f("ix_transfer_requests_payment_state"), table_name="transfer_requests"
    )
    op.drop_index(
        op.f("ix_transfer_requests_applied_tariff_id"), table_name="transfer_requests"
    )
    for column in (
        "commission_amount_snapshot",
        "commission_percent_snapshot",
        "payment_state",
        "applied_currency",
        "applied_price",
        "applied_tariff_id",
        "vehicle_id",
        "route_to_id",
        "route_from_id",
    ):
        op.drop_column("transfer_requests", column)

    op.drop_index(
        "uq_transfer_tariffs_current",
        table_name="transfer_tariffs",
        postgresql_where=sa.text("effective_to IS NULL"),
    )
    op.drop_index("ix_transfer_tariffs_route", table_name="transfer_tariffs")
    op.drop_table("transfer_tariffs")
    op.drop_index(
        op.f("ix_transfer_vehicles_vehicle_type"), table_name="transfer_vehicles"
    )
    op.drop_index(op.f("ix_transfer_vehicles_plate"), table_name="transfer_vehicles")
    op.drop_index(
        op.f("ix_transfer_vehicles_is_active"), table_name="transfer_vehicles"
    )
    op.drop_table("transfer_vehicles")
    op.drop_index(op.f("ix_transfer_locations_kind"), table_name="transfer_locations")
    op.drop_index(
        op.f("ix_transfer_locations_is_active"), table_name="transfer_locations"
    )
    op.drop_table("transfer_locations")
