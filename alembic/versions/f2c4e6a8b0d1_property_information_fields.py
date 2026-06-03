"""property information fields

Revision ID: f2c4e6a8b0d1
Revises: f0e1d2c3b4a5
Create Date: 2026-06-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2c4e6a8b0d1"
down_revision: str | None = "f0e1d2c3b4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sanatoriums", sa.Column("postal_code", sa.String(length=20)))
    op.add_column(
        "sanatoriums", sa.Column("customer_support_email", sa.String(length=255))
    )
    op.add_column("sanatoriums", sa.Column("renovation_year", sa.SmallInteger()))
    op.add_column("sanatoriums", sa.Column("chain_name", sa.String(length=120)))
    op.add_column(
        "sanatoriums",
        sa.Column(
            "host_type",
            sa.Enum(
                "private_host",
                "professional_host",
                name="hosttype",
                native_enum=False,
                length=30,
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("sanatoriums", "host_type")
    op.drop_column("sanatoriums", "chain_name")
    op.drop_column("sanatoriums", "renovation_year")
    op.drop_column("sanatoriums", "customer_support_email")
    op.drop_column("sanatoriums", "postal_code")
