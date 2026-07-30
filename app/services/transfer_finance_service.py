"""Commission-based settlement view for the transfer operator.

Deliberately separate from ``finance_service``: that one splits a booking
between the platform and the sanatorium, while a transfer is settled with the
transfer operator under their own commission percentage.
"""

from datetime import UTC, date, datetime, time

from fastapi import Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.models.booking import Booking
from app.models.transfer_request import (
    TransferPaymentState,
    TransferRequest,
    TransferStatus,
)
from app.services.finance_rules import ZERO, money

# Cancelled transfers keep their history but stop counting as revenue, the
# same way finance_reports treats cancelled bookings.
_ACTIVE = TransferRequest.status != TransferStatus.CANCELLED
_PRICED = TransferRequest.applied_price.isnot(None)


class TransferFinanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        currency: str | None = None,
    ) -> dict:
        gross = func.coalesce(TransferRequest.applied_price, 0)
        commission = func.coalesce(TransferRequest.commission_amount_snapshot, 0)
        unpaid = case(
            (
                TransferRequest.payment_state == TransferPaymentState.UNPAID,
                gross,
            ),
            else_=0,
        )
        percent = TransferRequest.commission_percent_snapshot

        stmt = (
            select(
                TransferRequest.applied_currency.label("currency"),
                func.count(TransferRequest.id).label("order_count"),
                func.coalesce(func.sum(gross), 0).label("gross_amount"),
                func.coalesce(func.sum(commission), 0).label("commission_amount"),
                func.coalesce(func.sum(gross - commission), 0).label("net_amount"),
                func.coalesce(func.sum(unpaid), 0).label("unpaid_amount"),
                # One percentage only makes sense when every row shares it.
                case(
                    (func.min(percent) == func.max(percent), func.min(percent)),
                    else_=None,
                ).label("commission_percent"),
            )
            .group_by(TransferRequest.applied_currency)
            .order_by(TransferRequest.applied_currency)
        )
        stmt = self._apply_filters(
            stmt, date_from=date_from, date_to=date_to, currency=currency
        )
        rows = (await self.db.execute(stmt)).all()
        return {
            "items": [
                {
                    "currency": row.currency,
                    "order_count": int(row.order_count),
                    "gross_amount": money(row.gross_amount),
                    "platform_commission_percent": row.commission_percent,
                    "platform_commission_amount": money(row.commission_amount),
                    "net_payout_amount": money(row.net_amount),
                    "unpaid_amount": money(row.unpaid_amount),
                }
                for row in rows
            ]
        }

    async def orders(
        self,
        *,
        limit: int,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        currency: str | None = None,
    ) -> tuple[list[dict], int]:
        stmt = select(TransferRequest).order_by(TransferRequest.created_at.desc())
        stmt = self._apply_filters(
            stmt, date_from=date_from, date_to=date_to, currency=currency
        )
        rows, total = await paginated(self.db, stmt, limit=limit, offset=offset)
        codes = await self._booking_codes([r.booking_id for r in rows])
        return [self._order_item(r, codes.get(r.booking_id)) for r in rows], total

    async def _booking_codes(self, booking_ids: list) -> dict:
        wanted = {bid for bid in booking_ids if bid is not None}
        if not wanted:
            return {}
        rows = (
            await self.db.execute(
                select(Booking.id, Booking.code).where(Booking.id.in_(wanted))
            )
        ).all()
        return {row.id: row.code for row in rows}

    @staticmethod
    def _order_item(transfer: TransferRequest, booking_code: str | None) -> dict:
        gross = money(transfer.applied_price)
        commission = money(transfer.commission_amount_snapshot)
        active = transfer.status != TransferStatus.CANCELLED
        return {
            "transfer_id": transfer.id,
            "booking_id": transfer.booking_id,
            "booking_code": booking_code,
            "direction": transfer.direction,
            "vehicle_type": transfer.vehicle_type,
            "pickup_location": transfer.pickup_location,
            "dropoff_location": transfer.dropoff_location,
            "status": transfer.status,
            "payment_state": transfer.payment_state,
            "gross_amount": gross if active else ZERO,
            "platform_commission_percent": transfer.commission_percent_snapshot,
            "platform_commission_amount": commission if active else ZERO,
            "net_payout_amount": (gross - commission) if active else ZERO,
            "currency": transfer.applied_currency or "",
            "created_at": transfer.created_at,
        }

    @staticmethod
    def _apply_filters(
        stmt,
        *,
        date_from: date | None,
        date_to: date | None,
        currency: str | None,
    ):
        stmt = stmt.where(_ACTIVE, _PRICED)
        if date_from is not None:
            stmt = stmt.where(
                TransferRequest.created_at
                >= datetime.combine(date_from, time.min, tzinfo=UTC)
            )
        if date_to is not None:
            stmt = stmt.where(
                TransferRequest.created_at
                <= datetime.combine(date_to, time.max, tzinfo=UTC)
            )
        if currency is not None:
            stmt = stmt.where(
                TransferRequest.applied_currency == currency.strip().upper()
            )
        return stmt


def get_transfer_finance_service(
    db: AsyncSession = Depends(get_db),
) -> TransferFinanceService:
    return TransferFinanceService(db)
