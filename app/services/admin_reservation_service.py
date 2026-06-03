from datetime import UTC, date, datetime, time, timedelta

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import TASHKENT_TZ, pick_locale, today_tashkent
from app.models.booking import Booking, BookingStatus
from app.models.review import ReviewReplyStatus, SanatoriumReview
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User
from app.models.user import UserRole
from app.schemas.booking import (
    AdminGuestActivity,
    AdminReservationDashboard,
    AdminReservationDashboardStats,
    AdminReservationListItem,
)
from app.services.booking_visibility import booking_visibility_clauses


class AdminReservationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dashboard(
        self, user: User, *, activity_date: date | None, unprocessed_limit: int
    ) -> AdminReservationDashboard:
        day = activity_date or today_tashkent()
        start, end = _day_bounds(day)
        visible = booking_visibility_clauses(user)
        active = Booking.status != BookingStatus.CANCELLED

        reservations_today = await self._count(
            *visible, Booking.created_at >= start, Booking.created_at < end
        )
        checking_in_today = await self._count(*visible, active, Booking.check_in == day)
        unprocessed_count = await self._count(*visible, Booking.is_processed.is_(False))

        return AdminReservationDashboard(
            stats=AdminReservationDashboardStats(
                reservations_made_today=reservations_today,
                checking_in_today=checking_in_today,
                unreplied_reviews=await self._unreplied_reviews_count(user),
                unanswered_questions=0,
                unprocessed_reservations=unprocessed_count,
            ),
            unprocessed=await self._items(
                *visible,
                Booking.is_processed.is_(False),
                limit=unprocessed_limit,
            ),
            guest_activity=AdminGuestActivity(
                check_ins=await self._items(*visible, active, Booking.check_in == day),
                in_house=await self._items(
                    *visible, active, Booking.check_in <= day, Booking.check_out > day
                ),
                check_outs=await self._items(
                    *visible, active, Booking.check_out == day
                ),
            ),
        )

    async def _count(self, *clauses) -> int:
        stmt = select(func.count(Booking.id))
        for clause in clauses:
            stmt = stmt.where(clause)
        return await self.db.scalar(stmt) or 0

    async def _unreplied_reviews_count(self, user: User) -> int:
        stmt = select(func.count(SanatoriumReview.id)).where(
            SanatoriumReview.is_visible.is_(True),
            SanatoriumReview.reply_status == ReviewReplyStatus.AWAITING_REPLY,
        )
        if user.role == UserRole.ADMIN:
            stmt = stmt.where(
                SanatoriumReview.sanatorium_id.in_(
                    select(Sanatorium.id).where(Sanatorium.admin_user_id == user.id)
                )
            )
        return await self.db.scalar(stmt) or 0

    async def _items(
        self,
        *clauses,
        limit: int = 20,
    ) -> list[AdminReservationListItem]:
        stmt = (
            select(Booking, User.full_name, User.email, Room.name.label("room_name"))
            .outerjoin(User, Booking.user_id == User.id)
            .outerjoin(Room, Booking.room_id == Room.id)
        )
        for clause in clauses:
            stmt = stmt.where(clause)
        stmt = stmt.order_by(Booking.created_at.desc()).limit(limit)
        return [
            _admin_item_from_row(row) for row in (await self.db.execute(stmt)).all()
        ]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TASHKENT_TZ).astimezone(UTC)
    return start, start + timedelta(days=1)


def _admin_item_from_row(row) -> AdminReservationListItem:
    booking, full_name, email, room_name = row
    return AdminReservationListItem(
        id=booking.id,
        code=booking.code,
        reservation_number=booking.reservation_number,
        guest_name=_guest_name(booking, full_name, email),
        amount=booking.final_price,
        currency=booking.currency,
        check_in=booking.check_in,
        check_out=booking.check_out,
        room_type=pick_locale(room_name),
        rooms_count=booking.rooms_count,
        booking_date=booking.created_at,
        status=booking.status,
        is_processed=booking.is_processed,
        has_special_requests=bool(booking.special_requests),
    )


def _guest_name(booking: Booking, full_name: str | None, email: str | None) -> str:
    for item in booking.guest_details or []:
        name = item.get("full_name") if isinstance(item, dict) else None
        if name:
            return name
    return full_name or email or "Guest"


def get_admin_reservation_service(
    db: AsyncSession = Depends(get_db),
) -> AdminReservationService:
    return AdminReservationService(db)
