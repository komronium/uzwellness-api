"""sanatorium name as JSONB translations

Revision ID: c9f8a3b1e4d2
Revises: b6c4d9e3f0a2
Create Date: 2026-05-19 12:00:00
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9f8a3b1e4d2"
down_revision: Union[str, None] = "b6c4d9e3f0a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_sanatoriums_name", table_name="sanatoriums")
    op.execute(
        "ALTER TABLE sanatoriums "
        "ALTER COLUMN name TYPE JSONB USING jsonb_build_object('uz', name)"
    )
    op.alter_column(
        "sanatoriums",
        "name",
        server_default=sa.text("'{}'::jsonb"),
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sanatoriums",
        "name",
        server_default=None,
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
    )
    op.execute(
        "ALTER TABLE sanatoriums "
        "ALTER COLUMN name TYPE VARCHAR(255) "
        "USING COALESCE(name->>'uz', name->>'ru', name->>'en', '')"
    )
    op.create_index(
        "ix_sanatoriums_name", "sanatoriums", ["name"], unique=False
    )
