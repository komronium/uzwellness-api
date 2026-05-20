from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.notifier import BookingNotifier
from app.core.utils import pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.package import Package
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.email_service import BookingEmailContext

_CENTS = Decimal("0.01")


class PackageBookingFlow:
    """Package booking — `final_price = base_price × guests`.

    `check_out = check_in + duration_nights` if the client doesn't pass one.
    No availability locking — packages are sold against a curated allocation
    handled offline (flights, transfers, etc.).
    """

    booking_type = BookingType.PACKAGE

    def __init__(
        self,
        db: AsyncSession,
        pricing: BookingPricingPolicy,
        notifier: BookingNotifier,
    ) -> None:
        self.db = db
        self.pricing = pricing
        self.notifier = notifier

    def matches(self, payload: BookingCreate) -> bool:
        return payload.package_id is not None

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        package = (
            await self.db.execute(
                select(Package).where(Package.id == payload.package_id)
            )
        ).scalar_one_or_none()
        if package is None or not package.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
            )

        sanatorium = None
        if package.sanatorium_id is not None:
            sanatorium = (
                await self.db.execute(
                    select(Sanatorium).where(Sanatorium.id == package.sanatorium_id)
                )
            ).scalar_one_or_none()
            if sanatorium is not None and sanatorium.status != SanatoriumStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sanatorium is not available for booking",
                )

        check_out = payload.check_out or (
            payload.check_in + timedelta(days=package.duration_nights)
        )
        if check_out <= payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be after check_in",
            )

        is_b2b = user.role == UserRole.AGENT
        base_total = (package.base_price * payload.guests).quantize(
            _CENTS, ROUND_HALF_UP
        )
        pricing = await self.pricing.apply(
            base_total=base_total,
            sanatorium=sanatorium,
            user=user,
            is_b2b=is_b2b,
            payload=payload,
        )

        booking = Booking(
            user_id=user.id,
            package_id=package.id,
            booking_type=BookingType.PACKAGE,
            check_in=payload.check_in,
            check_out=check_out,
            guests=payload.guests,
            status=BookingStatus.CONFIRMED,
            final_price=pricing.final_price,
            currency=package.currency,
            is_b2b=is_b2b,
            b2b_client_price=pricing.b2b_client_price,
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
            ),
        )
        self.db.add(booking)
        await self.db.flush()
        self.db.add(
            Notification(
                booking_id=booking.id, type="booking_created", channel="email"
            )
        )
        await self.db.commit()

        display_name = (
            pick_locale(sanatorium.name) if sanatorium is not None
            else pick_locale(package.title)
        )
        await self._send_received_email(booking, user, display_name)
        return await self._load(booking.id)

    async def _load(self, booking_id) -> Booking:
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .where(Booking.id == booking_id)
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def _send_received_email(
        self, booking: Booking, user: User, display_name: str
    ) -> None:
        if not user.email:
            return
        ctx = BookingEmailContext(
            booking_code=booking.code,
            sanatorium_name=display_name,
            check_in=booking.check_in,
            check_out=booking.check_out,
            guest_name=user.full_name or user.email,
            total_price=booking.final_price,
            currency=booking.currency,
        )
        self.notifier.booking_received(to=user.email, ctx=ctx)
