"""i18n columns: amenity/room/extra_bed description + sanatorium address JSONB

Revision ID: a1b2c3d4e5f6
Revises: c9f8a3b1e4d2
Create Date: 2026-05-20 14:00:00
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c9f8a3b1e4d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "amenities",
        sa.Column(
            "description",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "rooms",
        sa.Column(
            "description",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "extra_bed_configs",
        sa.Column(
            "description",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "ALTER TABLE sanatoriums "
        "ALTER COLUMN address TYPE JSONB USING jsonb_build_object('uz', address)"
    )
    op.alter_column(
        "sanatoriums",
        "address",
        server_default=sa.text("'{}'::jsonb"),
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sanatoriums",
        "address",
        server_default=None,
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
    )
    op.execute(
        "ALTER TABLE sanatoriums "
        "ALTER COLUMN address TYPE VARCHAR(500) "
        "USING COALESCE(address->>'uz', address->>'ru', address->>'en', '')"
    )
    op.drop_column("extra_bed_configs", "description")
    op.drop_column("rooms", "description")
    op.drop_column("amenities", "description")
