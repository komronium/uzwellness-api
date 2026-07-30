"""uzum payments: cancelled_at, transId uniqueness, retire payme/click

Revision ID: 51f31913df6c
Revises: b2c3d4e5f6a7
Create Date: 2026-07-30 12:31:43.154333

Uzum Bank replaces Payme and Click as the online payment provider. Legacy
payme/click rows would no longer load through the ``PaymentMethod`` enum, so
they are parked on ``cash`` with the original method kept in ``raw_payload``
under ``legacy_method`` (nothing is deleted, and the downgrade restores them).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "51f31913df6c"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UZUM_INDEX_WHERE = sa.text("method = 'uzum' AND provider_payment_id IS NOT NULL")


def upgrade() -> None:
    op.add_column(
        "payments", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "uq_payments_uzum_provider_payment_id",
        "payments",
        ["provider_payment_id"],
        unique=True,
        postgresql_where=_UZUM_INDEX_WHERE,
    )
    op.execute(
        """
        UPDATE payments
           SET raw_payload = coalesce(raw_payload, '{}'::jsonb)
                             || jsonb_build_object('legacy_method', method),
               method = 'cash'
         WHERE method IN ('payme', 'click')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE payments
           SET method = raw_payload ->> 'legacy_method',
               raw_payload = raw_payload - 'legacy_method'
         WHERE raw_payload ? 'legacy_method'
        """
    )
    op.drop_index(
        "uq_payments_uzum_provider_payment_id",
        table_name="payments",
        postgresql_where=_UZUM_INDEX_WHERE,
    )
    op.drop_column("payments", "cancelled_at")
