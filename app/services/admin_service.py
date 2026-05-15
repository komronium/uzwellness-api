from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.room import ExchangeRate, Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User

_USD_UZS = "USD_UZS"
_TWELVE_MONTHS = 12


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_stats(self) -> dict:
        rate = await self._usd_uzs_rate()
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        active_status = Booking.status != BookingStatus.CANCELLED

        total_bookings = (await self.db.execute(
            select(func.count(Booking.id)).where(active_status)
        )).scalar_one()
        bookings_this_month = (await self.db.execute(
            select(func.count(Booking.id)).where(
                active_status, Booking.created_at >= month_start
            )
        )).scalar_one()

        total_revenue_usd = await self._revenue_usd(rate, since=None)
        revenue_this_month_usd = await self._revenue_usd(rate, since=month_start)

        total_users = (await self.db.execute(
            select(func.count(User.id))
        )).scalar_one()
        new_users_this_month = (await self.db.execute(
            select(func.count(User.id)).where(User.created_at >= month_start)
        )).scalar_one()

        total_sanatoriums = (await self.db.execute(
            select(func.count(Sanatorium.id))
        )).scalar_one()
        pending_sanatoriums = (await self.db.execute(
            select(func.count(Sanatorium.id)).where(
                Sanatorium.status == SanatoriumStatus.PENDING
            )
        )).scalar_one()

        top_sanatoriums = await self._top_sanatoriums(rate, limit=5)
        monthly_revenue = await self._monthly_revenue(rate)

        return {
            "total_bookings": total_bookings,
            "bookings_this_month": bookings_this_month,
            "total_revenue_usd": total_revenue_usd,
            "revenue_this_month_usd": revenue_this_month_usd,
            "total_users": total_users,
            "new_users_this_month": new_users_this_month,
            "total_sanatoriums": total_sanatoriums,
            "pending_sanatoriums": pending_sanatoriums,
            "top_sanatoriums": top_sanatoriums,
            "monthly_revenue": monthly_revenue,
        }

    async def _usd_uzs_rate(self) -> Decimal:
        rate = (await self.db.execute(
            select(ExchangeRate.rate).where(ExchangeRate.pair == _USD_UZS)
        )).scalar_one_or_none()
        return rate if rate and rate > 0 else Decimal("1")

    @staticmethod
    def _usd_expr(rate: Decimal):
        return case(
            (Booking.currency == "USD", Booking.final_price),
            else_=Booking.final_price / rate,
        )

    async def _revenue_usd(self, rate: Decimal, *, since: datetime | None) -> Decimal:
        stmt = select(func.coalesce(func.sum(self._usd_expr(rate)), 0)).where(
            Booking.status != BookingStatus.CANCELLED
        )
        if since is not None:
            stmt = stmt.where(Booking.created_at >= since)
        value = (await self.db.execute(stmt)).scalar_one()
        return Decimal(value).quantize(Decimal("0.01"))

    async def _top_sanatoriums(self, rate: Decimal, *, limit: int) -> list[dict]:
        usd_expr = self._usd_expr(rate)
        room_subq = (
            select(
                Room.sanatorium_id.label("sid"),
                func.count(Booking.id).label("cnt"),
                func.coalesce(func.sum(usd_expr), 0).label("rev"),
            )
            .join(Booking, Booking.room_id == Room.id)
            .where(Booking.status != BookingStatus.CANCELLED)
            .group_by(Room.sanatorium_id)
            .subquery()
        )
        stmt = (
            select(
                Sanatorium.id,
                Sanatorium.name,
                func.coalesce(room_subq.c.cnt, 0).label("booking_count"),
                func.coalesce(room_subq.c.rev, 0).label("revenue"),
            )
            .outerjoin(room_subq, Sanatorium.id == room_subq.c.sid)
            .order_by(
                func.coalesce(room_subq.c.rev, 0).desc(),
                func.coalesce(room_subq.c.cnt, 0).desc(),
            )
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "booking_count": int(row.booking_count),
                "revenue": Decimal(row.revenue).quantize(Decimal("0.01")),
            }
            for row in rows
        ]

    async def _monthly_revenue(self, rate: Decimal) -> list[dict]:
        usd_expr = self._usd_expr(rate)
        bucket = func.to_char(Booking.created_at, "YYYY-MM").label("month")
        since = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=31 * (_TWELVE_MONTHS - 1))
        stmt = (
            select(bucket, func.coalesce(func.sum(usd_expr), 0).label("revenue"))
            .where(
                Booking.status != BookingStatus.CANCELLED,
                Booking.created_at >= since,
            )
            .group_by(bucket)
            .order_by(bucket.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "month": row.month,
                "revenue": Decimal(row.revenue).quantize(Decimal("0.01")),
            }
            for row in rows
        ]


def get_admin_service(db: AsyncSession = Depends(get_db)) -> AdminService:
    return AdminService(db)
