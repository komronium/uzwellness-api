"""add image metadata

Revision ID: f1a2b3c4d5e6
Revises: e7c9a1d5b2f0
Create Date: 2026-05-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e7c9a1d5b2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_image_metadata(table: str) -> None:
    op.add_column(
        table,
        sa.Column("is_360", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(table, sa.Column("category", sa.String(length=40), nullable=True))
    op.add_column(
        table,
        sa.Column(
            "caption_i18n",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "alt_text",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def _drop_image_metadata(table: str) -> None:
    op.drop_column(table, "tags")
    op.drop_column(table, "alt_text")
    op.drop_column(table, "caption_i18n")
    op.drop_column(table, "category")
    op.drop_column(table, "is_360")


def upgrade() -> None:
    """Upgrade schema."""
    _add_image_metadata("sanatorium_images")
    _add_image_metadata("room_images")


def downgrade() -> None:
    """Downgrade schema."""
    _drop_image_metadata("room_images")
    _drop_image_metadata("sanatorium_images")
