"""uzum checkout: one payment per Checkout orderId

Revision ID: a1c4e9d27b53
Revises: 3ad7b0102e8b
Create Date: 2026-08-12 21:10:00.000000

Checkout payments live in the same ``payments`` table under the new
``uzum_checkout`` method. The partial unique index mirrors the Merchant API
one: a redelivered callback for an ``orderId`` can only ever touch the single
row that owns it.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c4e9d27b53"
down_revision: Union[str, Sequence[str], None] = "3ad7b0102e8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WHERE = sa.text("method = 'uzum_checkout' AND provider_payment_id IS NOT NULL")


def upgrade() -> None:
    op.create_index(
        "uq_payments_uzum_checkout_order_id",
        "payments",
        ["provider_payment_id"],
        unique=True,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_payments_uzum_checkout_order_id", table_name="payments")
