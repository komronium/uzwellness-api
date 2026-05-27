import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db
from app.core.discount_tiers import best_tier_discount_percent, next_tier
from app.core.utils import pick_locale
from app.models.booking import Booking, BookingStatus
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User

_CENTS = Decimal("0.01")


def _year_start(now: datetime) -> datetime:
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


class B2BService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dashboard(self, agent: User) -> dict:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_start = _year_start(now)
        owned = Booking.user_id == agent.id
        not_cancelled = Booking.status != BookingStatus.CANCELLED

        total_bookings, bookings_this_month, bookings_this_year = (
            await self.db.execute(
                select(
                    func.count(Booking.id).filter(owned),
                    func.count(Booking.id).filter(
                        owned, Booking.created_at >= month_start
                    ),
                    func.count(Booking.id).filter(
                        owned, Booking.created_at >= year_start
                    ),
                )
            )
        ).one()

        total_paid = await self.db.scalar(
            select(
                func.coalesce(
                    func.sum(Booking.final_price).filter(owned, not_cancelled), 0
                )
            )
        )

        current_year_bookings = await self.db.scalar(
            select(func.count(Booking.id)).where(
                owned,
                Booking.is_b2b.is_(True),
                not_cancelled,
                Booking.created_at >= year_start,
            )
        )

        return {
            "total_bookings": total_bookings or 0,
            "bookings_this_month": bookings_this_month or 0,
            "bookings_this_year": bookings_this_year or 0,
            "total_paid": Decimal(total_paid).quantize(_CENTS),
            "current_year_bookings": int(current_year_bookings or 0),
        }

    async def discount_status(self, agent: User, sanatorium_id: uuid.UUID) -> dict:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sanatorium not found",
            )

        year_start = _year_start(datetime.now(UTC))
        count = await self.db.scalar(
            select(func.count(Booking.id)).where(
                Booking.user_id == agent.id,
                Booking.is_b2b.is_(True),
                Booking.status != BookingStatus.CANCELLED,
                Booking.created_at >= year_start,
                self._booking_belongs_to_sanatorium(sanatorium_id),
            )
        )
        current = int(count or 0)

        tiers = sanatorium.agent_discount_tiers or []
        return {
            "sanatorium_id": sanatorium.id,
            "current_year_bookings": current,
            "current_tier_discount_percent": best_tier_discount_percent(tiers, current),
            "next_tier": next_tier(tiers, current),
        }

    async def orders(
        self, agent: User, *, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        owned = Booking.user_id == agent.id

        total = await self.db.scalar(select(func.count(Booking.id)).where(owned))

        room_sanatorium = aliased(Sanatorium)
        program_sanatorium = aliased(Sanatorium)
        package_sanatorium = aliased(Sanatorium)

        rows = (
            await self.db.execute(
                select(Booking)
                .add_columns(
                    func.coalesce(
                        room_sanatorium.name,
                        program_sanatorium.name,
                        package_sanatorium.name,
                        Package.title,
                    ).label("sanatorium_name")
                )
                .outerjoin(Room, Booking.room_id == Room.id)
                .outerjoin(room_sanatorium, Room.sanatorium_id == room_sanatorium.id)
                .outerjoin(TreatmentProgram, Booking.program_id == TreatmentProgram.id)
                .outerjoin(
                    program_sanatorium,
                    TreatmentProgram.sanatorium_id == program_sanatorium.id,
                )
                .outerjoin(Package, Booking.package_id == Package.id)
                .outerjoin(
                    package_sanatorium,
                    Package.sanatorium_id == package_sanatorium.id,
                )
                .where(owned)
                .order_by(Booking.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        items: list[dict] = []
        for booking, name_dict in rows:
            items.append(
                {
                    "booking_id": booking.id,
                    "booking_code": booking.code,
                    "sanatorium_name": pick_locale(name_dict) if name_dict else None,
                    "price_paid": booking.final_price,
                    "agent_discount_percent": booking.agent_discount_percent_snapshot,
                    "currency": booking.currency,
                    "check_in": booking.check_in,
                    "check_out": booking.check_out,
                    "status": booking.status,
                    "created_at": booking.created_at,
                }
            )
        return items, int(total or 0)

    @staticmethod
    def _booking_belongs_to_sanatorium(sanatorium_id: uuid.UUID):
        room_sub = (
            select(Room.id).where(Room.sanatorium_id == sanatorium_id).scalar_subquery()
        )
        program_sub = (
            select(TreatmentProgram.id)
            .where(TreatmentProgram.sanatorium_id == sanatorium_id)
            .scalar_subquery()
        )
        package_sub = (
            select(Package.id)
            .where(Package.sanatorium_id == sanatorium_id)
            .scalar_subquery()
        )
        return (
            Booking.room_id.in_(room_sub)
            | Booking.program_id.in_(program_sub)
            | Booking.package_id.in_(package_sub)
        )


def get_b2b_service(db: AsyncSession = Depends(get_db)) -> B2BService:
    return B2BService(db)
