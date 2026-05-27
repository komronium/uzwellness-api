"""add performance indexes

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-05-27 23:35:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_sanatoriums_public_list",
        "sanatoriums",
        ["status", "property_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_sanatoriums_status_rating",
        "sanatoriums",
        ["status", "avg_rating"],
        unique=False,
    )
    op.create_index(
        "ix_sanatoriums_treatment_focuses_gin",
        "sanatoriums",
        ["treatment_focuses"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_sanatoriums_name_gin",
        "sanatoriums",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "jsonb_path_ops"},
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sanatoriums_name_uz_text_trgm "
        "ON sanatoriums USING gin ((name ->> 'uz') gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sanatoriums_name_ru_text_trgm "
        "ON sanatoriums USING gin ((name ->> 'ru') gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sanatoriums_name_en_text_trgm "
        "ON sanatoriums USING gin ((name ->> 'en') gin_trgm_ops)"
    )
    op.create_index(
        "ix_rooms_search_available",
        "rooms",
        ["sanatorium_id", "is_active", "base_price"],
        unique=False,
    )
    op.create_index(
        "ix_bookings_user_created",
        "bookings",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_user_created", table_name="bookings")
    op.drop_index("ix_rooms_search_available", table_name="rooms")
    op.execute("DROP INDEX IF EXISTS ix_sanatoriums_name_en_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_sanatoriums_name_ru_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_sanatoriums_name_uz_text_trgm")
    op.drop_index("ix_sanatoriums_name_gin", table_name="sanatoriums")
    op.drop_index("ix_sanatoriums_treatment_focuses_gin", table_name="sanatoriums")
    op.drop_index("ix_sanatoriums_status_rating", table_name="sanatoriums")
    op.drop_index("ix_sanatoriums_public_list", table_name="sanatoriums")
