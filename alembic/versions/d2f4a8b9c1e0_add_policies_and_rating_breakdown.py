"""add policies and rating breakdown

Revision ID: d2f4a8b9c1e0
Revises: ab33125db2d5
Create Date: 2026-05-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2f4a8b9c1e0"
down_revision: Union[str, Sequence[str], None] = "ab33125db2d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sanatoriums",
        sa.Column(
            "policies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatoriums",
        sa.Column(
            "rating_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatorium_reviews", sa.Column("amenities", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "sanatorium_reviews", sa.Column("treatment", sa.SmallInteger(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sanatorium_reviews", "treatment")
    op.drop_column("sanatorium_reviews", "amenities")
    op.drop_column("sanatoriums", "rating_breakdown")
    op.drop_column("sanatoriums", "policies")
