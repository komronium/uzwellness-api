"""rename rooms sanatorium_id index

Revision ID: 7c2e9a4b1d63
Revises: 601c80146dfd
Create Date: 2026-10-27 00:00:00.000000

Renaming room_categories to rooms kept the old index name, so the model's
`ix_rooms_sanatorium_id` never matched and `alembic check` / autogenerate
reported a drop + create on every run. Rename in place: no rebuild, no lock
beyond the catalog update.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7c2e9a4b1d63"
down_revision: str | None = "601c80146dfd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER INDEX IF EXISTS ix_room_categories_sanatorium_id "
        "RENAME TO ix_rooms_sanatorium_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX IF EXISTS ix_rooms_sanatorium_id "
        "RENAME TO ix_room_categories_sanatorium_id"
    )
