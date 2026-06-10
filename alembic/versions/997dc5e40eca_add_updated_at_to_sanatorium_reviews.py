"""add updated_at to sanatorium_reviews

Revision ID: 997dc5e40eca
Revises: 3b7c1d2e4f50
Create Date: 2026-06-10 22:12:17.710366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '997dc5e40eca'
down_revision: Union[str, Sequence[str], None] = '3b7c1d2e4f50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sanatorium_reviews',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sanatorium_reviews', 'updated_at')
