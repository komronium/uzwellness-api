import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pricing import calculate_stay_total
from app.core.utils import date_range, today_tashkent
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.extra_bed import BookingExtraBed, ExtraBedConfig
from app.models.notification import Notification
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.email_service import (
    BookingEmailContext,
    send_booking_cancelled,
    send_booking_received,
)

_CANCELLABLE = {BookingStatus.PENDING, BookingStatus.CONFIRMED}
_CENTS = Decimal("0.01")
_PERCENT = Decimal("0.01")
_ZERO = Decimal("0")


def _apply_percent(amount: Decimal, percent: Decimal) -> Decimal:
    return (amount * percent / Decimal("100")).quantize(_CENTS, ROUND_HALF_UP)


def _tier_discount_percent(tiers: list | None, current_year_bookings: int) -> Decimal:
    if not tiers:
        return _ZERO
    best = _ZERO
    for tier in tiers:
        try:
            min_bookings = int(tier["min_bookings"])
            discount = Decimal(str(tier["discount_percent"]))
        except (KeyError, TypeError, ValueError):
            continue
        if current_year_bookings >= min_bookings and discount > best:
            best = discount
    return best


class BookingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        if payload.check_in < today_tashkent():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_in must be today or in the future",
            )

        if payload.program_id is not None:
            return await self._create_session(payload, user)
        return await self._create_room(payload, user)

    async def _create_room(self, payload: BookingCreate, user: User) -> Booking:
        if payload.check_out is None or payload.check_out <= payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be after check_in",
            )

        nights = (payload.check_out - payload.check_in).days
        all_dates = date_range(payload.check_in, payload.check_out)

        room = (
            await self.db.execute(
                select(Room)
                .where(Room.id == payload.room_id)
                .options(selectinload(Room.price_periods))
                .with_for_update(of=Room)
            )
        ).scalar_one_or_none()
        if room is None or not room.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )

        sanatorium = await self._approved_sanatorium(room.sanatorium_id)

        if nights < room.min_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Minimum stay is {room.min_nights} night(s)",
            )
        if room.capacity < payload.guests:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Room capacity is {room.capacity} guest(s)",
            )

        avail_rows = list(
            (
                await self.db.execute(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_id == room.id,
                        RoomAvailability.date.in_(all_dates),
                    )
                    .with_for_update()
                )
            ).scalars()
        )
        if len(avail_rows) != nights:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not all dates are available",
            )
        for row in avail_rows:
            if row.units_available < 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No units available on {row.date}",
                )

        for row in avail_rows:
            row.units_available -= 1

        is_b2b = user.role == UserRole.AGENT
        room_total = calculate_stay_total(room, list(all_dates), room.price_periods)
        extra_bed_records = await self._build_extra_beds(
            payload, room.sanatorium_id, nights
        )
        agent_discount_percent = (
            await self._agent_tier_discount(user, sanatorium) if is_b2b else _ZERO
        )
        if agent_discount_percent > _ZERO:
            room_total = (
                room_total * (Decimal("1") - agent_discount_percent / Decimal("100"))
            ).quantize(_CENTS, ROUND_HALF_UP)
        b2b_client_price = self._resolve_b2b_client_price(payload, is_b2b, room_total)
        commission_percent, commission_amount = self._commission_snapshot(
            sanatorium, room_total, is_b2b
        )

        booking = Booking(
            user_id=user.id,
            room_id=room.id,
            booking_type=BookingType.ROOM,
            check_in=payload.check_in,
            check_out=payload.check_out,
            guests=payload.guests,
            status=BookingStatus.CONFIRMED,
            final_price=room_total,
            currency=room.base_currency,
            is_b2b=is_b2b,
            b2b_client_price=b2b_client_price,
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=commission_amount,
            commission_percent_snapshot=commission_percent,
            agent_discount_percent_snapshot=(
                agent_discount_percent if is_b2b else None
            ),
        )
        self.db.add(booking)
        await self.db.flush()

        for eb in extra_bed_records:
            eb.booking_id = booking.id
            self.db.add(eb)

        self.db.add(
            Notification(booking_id=booking.id, type="booking_created", channel="email")
        )
        await self.db.commit()
        await self._notify(booking, user, sanatorium.name, kind="received")
        return await self._load(booking.id)  # type: ignore[return-value]

    async def _create_session(self, payload: BookingCreate, user: User) -> Booking:
        program = (
            await self.db.execute(
                select(TreatmentProgram).where(
                    TreatmentProgram.id == payload.program_id
                )
            )
        ).scalar_one_or_none()
        if program is None or not program.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
            )
        if program.price is None or program.currency is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Program is not bookable (no price set)",
            )
        sanatorium = await self._approved_sanatorium(program.sanatorium_id)

        if (
            program.group_size_max is not None
            and payload.guests > program.group_size_max
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {program.group_size_max} participant(s) per session",
            )

        check_out = payload.check_out or payload.check_in
        if check_out < payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be on or after check_in",
            )

        is_b2b = user.role == UserRole.AGENT
        total = (program.price * payload.guests).quantize(_CENTS, ROUND_HALF_UP)
        agent_discount_percent = (
            await self._agent_tier_discount(user, sanatorium) if is_b2b else _ZERO
        )
        if agent_discount_percent > _ZERO:
            total = (
                total * (Decimal("1") - agent_discount_percent / Decimal("100"))
            ).quantize(_CENTS, ROUND_HALF_UP)
        b2b_client_price = self._resolve_b2b_client_price(payload, is_b2b, total)
        commission_percent, commission_amount = self._commission_snapshot(
            sanatorium, total, is_b2b
        )
        booking = Booking(
            user_id=user.id,
            program_id=program.id,
            booking_type=BookingType.SESSION,
            check_in=payload.check_in,
            check_out=check_out,
            guests=payload.guests,
            status=BookingStatus.CONFIRMED,
            final_price=total,
            currency=program.currency,
            is_b2b=is_b2b,
            b2b_client_price=b2b_client_price,
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=commission_amount,
            commission_percent_snapshot=commission_percent,
            agent_discount_percent_snapshot=(
                agent_discount_percent if is_b2b else None
            ),
        )
        self.db.add(booking)
        await self.db.flush()

        self.db.add(
            Notification(booking_id=booking.id, type="booking_created", channel="email")
        )
        await self.db.commit()
        await self._notify(booking, user, sanatorium.name, kind="received")
        return await self._load(booking.id)  # type: ignore[return-value]

    async def list_for_user(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        is_b2b: bool | None = None,
        agent_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Booking], int]:
        def _apply(stmt):
            stmt = self._visibility_filter(stmt, user)
            if is_b2b is not None:
                stmt = stmt.where(Booking.is_b2b.is_(is_b2b))
            if agent_id is not None and user.role == UserRole.SUPER_ADMIN:
                stmt = stmt.where(Booking.user_id == agent_id)
            return stmt

        total = (
            await self.db.execute(
                select(func.count()).select_from(_apply(select(Booking)).subquery())
            )
        ).scalar_one()
        stmt = (
            _apply(select(Booking).options(selectinload(Booking.extra_beds)))
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def get_visible(self, booking_id: uuid.UUID, user: User) -> Booking | None:
        stmt = self._visibility_filter(
            select(Booking)
            .options(selectinload(Booking.extra_beds))
            .where(Booking.id == booking_id),
            user,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def cancel(self, booking: Booking, user: User) -> Booking:
        self._assert_can_cancel(booking, user)

        if booking.booking_type == BookingType.ROOM and booking.room_id is not None:
            avail_rows = list(
                (
                    await self.db.execute(
                        select(RoomAvailability)
                        .where(
                            RoomAvailability.room_id == booking.room_id,
                            RoomAvailability.date >= booking.check_in,
                            RoomAvailability.date < booking.check_out,
                        )
                        .with_for_update()
                    )
                ).scalars()
            )
            for row in avail_rows:
                row.units_available = min(row.units_available + 1, row.units_total)

        booking.status = BookingStatus.CANCELLED
        self.db.add(
            Notification(
                booking_id=booking.id, type="booking_cancelled", channel="email"
            )
        )
        await self.db.commit()

        sanatorium_name = await self._sanatorium_name_for(booking)
        if sanatorium_name is not None:
            await self._notify(booking, user, sanatorium_name, kind="cancelled")
        return await self._load(booking.id)  # type: ignore[return-value]

    @staticmethod
    def _commission_snapshot(
        sanatorium: Sanatorium, final_price: Decimal, is_b2b: bool
    ) -> tuple[Decimal, Decimal]:
        percent = (
            sanatorium.b2b_commission_percent
            if is_b2b
            else sanatorium.platform_commission_percent
        ) or _ZERO
        return percent, _apply_percent(final_price, percent)

    async def _agent_tier_discount(self, user: User, sanatorium: Sanatorium) -> Decimal:
        if not sanatorium.agent_discount_tiers:
            return _ZERO
        year_start = datetime(datetime.now(UTC).year, 1, 1, tzinfo=UTC)
        count = (
            await self.db.execute(
                select(func.count(Booking.id)).where(
                    Booking.user_id == user.id,
                    Booking.is_b2b.is_(True),
                    Booking.status != BookingStatus.CANCELLED,
                    Booking.created_at >= year_start,
                )
            )
        ).scalar_one()
        return _tier_discount_percent(sanatorium.agent_discount_tiers, int(count or 0))

    @staticmethod
    def _resolve_b2b_client_price(
        payload: BookingCreate, is_b2b: bool, agent_price: Decimal
    ) -> Decimal | None:
        if not is_b2b:
            return None
        if payload.b2b_client_price is None:
            return None
        if payload.b2b_client_price < agent_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="b2b_client_price cannot be lower than agent price",
            )
        return payload.b2b_client_price

    async def _approved_sanatorium(self, sanatorium_id: uuid.UUID) -> Sanatorium:
        sanatorium = (
            await self.db.execute(
                select(Sanatorium).where(Sanatorium.id == sanatorium_id)
            )
        ).scalar_one_or_none()
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium is not available for booking",
            )
        return sanatorium

    async def _build_extra_beds(
        self, payload: BookingCreate, sanatorium_id: uuid.UUID, nights: int
    ) -> list[BookingExtraBed]:
        records: list[BookingExtraBed] = []
        for item in payload.extra_beds:
            config = (
                await self.db.execute(
                    select(ExtraBedConfig).where(ExtraBedConfig.id == item.config_id)
                )
            ).scalar_one_or_none()
            if config is None or not config.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Extra bed config {item.config_id} not found",
                )
            if config.sanatorium_id != sanatorium_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Extra bed config does not belong to this sanatorium",
                )
            if item.count > config.max_count:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximum {config.max_count} of this bed type allowed",
                )
            total = (config.price_per_night * item.count * nights).quantize(
                _CENTS, ROUND_HALF_UP
            )
            records.append(
                BookingExtraBed(
                    config_id=config.id,
                    name_snapshot=config.name,
                    price_per_night_snapshot=config.price_per_night,
                    currency=config.currency,
                    count=item.count,
                    total_price=total,
                )
            )
        return records

    async def _load(self, booking_id: uuid.UUID) -> Booking | None:
        stmt = (
            select(Booking)
            .options(selectinload(Booking.extra_beds))
            .where(Booking.id == booking_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def _visibility_filter(self, stmt, user: User):
        if user.role == UserRole.SUPER_ADMIN:
            return stmt
        if user.role == UserRole.ADMIN:
            room_sub = (
                select(Room.id)
                .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
                .where(Sanatorium.admin_user_id == user.id)
                .scalar_subquery()
            )
            program_sub = (
                select(TreatmentProgram.id)
                .join(Sanatorium, TreatmentProgram.sanatorium_id == Sanatorium.id)
                .where(Sanatorium.admin_user_id == user.id)
                .scalar_subquery()
            )
            return stmt.where(
                Booking.room_id.in_(room_sub) | Booking.program_id.in_(program_sub)
            )
        return stmt.where(Booking.user_id == user.id)

    def _assert_can_cancel(self, booking: Booking, user: User) -> None:
        if booking.status not in _CANCELLABLE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Booking cannot be cancelled (status: {booking.status})",
            )
        if user.role in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
            return
        if booking.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to cancel this booking",
            )

    async def _notify(
        self,
        booking: Booking,
        user: User,
        sanatorium_name: str,
        *,
        kind: str,
    ) -> None:
        if not user.email:
            return
        ctx = BookingEmailContext(
            booking_code=booking.code,
            sanatorium_name=sanatorium_name,
            check_in=booking.check_in,
            check_out=booking.check_out,
            guest_name=user.full_name or user.email,
            total_price=booking.final_price,
            currency=booking.currency,
        )
        if kind == "received":
            send_booking_received(to=user.email, ctx=ctx)
        elif kind == "cancelled":
            send_booking_cancelled(to=user.email, ctx=ctx)

    async def build_invoice(self, booking: Booking) -> dict:
        sanatorium_name = await self._sanatorium_name_for(booking) or ""
        user = (
            (
                await self.db.execute(select(User).where(User.id == booking.user_id))
            ).scalar_one_or_none()
            if booking.user_id
            else None
        )
        nights = max((booking.check_out - booking.check_in).days, 1)
        subtotal = booking.final_price
        extras_total = sum((eb.total_price for eb in booking.extra_beds), Decimal("0"))
        line_items: list[dict] = [
            {
                "description": "Room/program",
                "qty": booking.guests,
                "amount": subtotal,
            }
        ]
        for eb in booking.extra_beds:
            line_items.append(
                {
                    "description": f"Extra bed × {eb.count}",
                    "qty": eb.count,
                    "amount": eb.total_price,
                }
            )
        return {
            "booking_code": booking.code,
            "issued_at": datetime.now(UTC),
            "customer_name": (user.full_name if user else None) or "",
            "customer_email": user.email if user else None,
            "sanatorium_name": sanatorium_name,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "nights": nights,
            "guests": booking.guests,
            "subtotal": subtotal,
            "total": subtotal + extras_total,
            "currency": booking.currency,
            "is_b2b": booking.is_b2b,
            "line_items": line_items,
        }

    async def _sanatorium_name_for(self, booking: Booking) -> str | None:
        if booking.room_id is not None:
            return (
                await self.db.execute(
                    select(Sanatorium.name)
                    .join(Room, Room.sanatorium_id == Sanatorium.id)
                    .where(Room.id == booking.room_id)
                )
            ).scalar_one_or_none()
        if booking.program_id is not None:
            return (
                await self.db.execute(
                    select(Sanatorium.name)
                    .join(
                        TreatmentProgram,
                        TreatmentProgram.sanatorium_id == Sanatorium.id,
                    )
                    .where(TreatmentProgram.id == booking.program_id)
                )
            ).scalar_one_or_none()
        return None


def get_booking_service(db: AsyncSession = Depends(get_db)) -> BookingService:
    return BookingService(db)
