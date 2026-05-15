from datetime import UTC, datetime
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import User

_CENTS = Decimal("0.01")


class B2BService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dashboard(self, agent: User) -> dict:
        month_start = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        active = Booking.user_id == agent.id
        cancelled = Booking.status == BookingStatus.CANCELLED

        total_bookings, bookings_this_month = (
            await self.db.execute(
                select(
                    func.count(Booking.id).filter(active),
                    func.count(Booking.id).filter(
                        active, Booking.created_at >= month_start
                    ),
                )
            )
        ).one()

        spent, commission = (
            await self.db.execute(
                select(
                    func.coalesce(
                        func.sum(Booking.final_price).filter(active, ~cancelled), 0
                    ),
                    func.coalesce(
                        func.sum(
                            Booking.b2b_client_price - Booking.final_price
                        ).filter(
                            active,
                            ~cancelled,
                            Booking.b2b_client_price.is_not(None),
                        ),
                        0,
                    ),
                )
            )
        ).one()

        return {
            "total_bookings": total_bookings or 0,
            "bookings_this_month": bookings_this_month or 0,
            "total_spent": Decimal(spent).quantize(_CENTS),
            "total_commission": Decimal(commission).quantize(_CENTS),
        }

    async def clients(
        self, agent: User, *, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        base = select(Booking).where(Booking.user_id == agent.id)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Booking.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()

        clients: list[dict] = []
        for booking in rows:
            for guest in booking.guest_details or []:
                clients.append(
                    {
                        "booking_id": booking.id,
                        "booking_code": booking.code,
                        "check_in": booking.check_in,
                        "check_out": booking.check_out,
                        **guest,
                    }
                )
        return clients, total


def get_b2b_service(db: AsyncSession = Depends(get_db)) -> B2BService:
    return B2BService(db)
