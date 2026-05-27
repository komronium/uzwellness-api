"""add_medical_base_to_sanatoriums

Revision ID: ab33125db2d5
Revises: 8bda2dd3cac0
Create Date: 2026-05-26 01:43:58.660282

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ab33125db2d5"
down_revision: Union[str, Sequence[str], None] = "8bda2dd3cac0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sanatoriums",
        sa.Column(
            "medical_base",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sanatoriums", "medical_base")
