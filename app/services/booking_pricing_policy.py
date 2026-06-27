from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.discount_tiers import best_tier_discount_percent
from app.models.booking import Booking, BookingStatus
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def apply_percent(amount: Decimal, percent: Decimal) -> Decimal:
    return (amount * percent / Decimal("100")).quantize(_CENTS, ROUND_HALF_UP)


class BookingPricingPolicy:
    """Cross-cutting pricing rules for both ROOM and SESSION bookings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def apply(
        self,
        *,
        base_total: Decimal,
        sanatorium: Sanatorium | None,
        user: User,
        is_b2b: bool,
    ) -> "BookingPricing":
        agent_discount_percent = (
            await self._agent_tier_discount(user, sanatorium)
            if is_b2b and sanatorium is not None
            else _ZERO
        )
        discounted = base_total
        if agent_discount_percent > _ZERO:
            discounted = (
                base_total * (Decimal("1") - agent_discount_percent / Decimal("100"))
            ).quantize(_CENTS, ROUND_HALF_UP)
        commission_percent, commission_amount = self._commission_snapshot(
            sanatorium, discounted, is_b2b
        )
        return BookingPricing(
            final_price=discounted,
            agent_discount_percent=agent_discount_percent,
            commission_percent=commission_percent,
            commission_amount=commission_amount,
        )

    async def agent_discount_for(
        self, user: User | None, sanatorium: Sanatorium | None
    ) -> Decimal:
        """Agent tier discount for display (room-offer search); 0 for non-agents.

        Mirrors the discount :meth:`apply` charges on a B2B booking, so the
        searched and the booked price match.
        """
        if user is None or sanatorium is None or user.role != UserRole.AGENT:
            return _ZERO
        return await self._agent_tier_discount(user, sanatorium)

    @staticmethod
    def _commission_snapshot(
        sanatorium: Sanatorium | None, final_price: Decimal, is_b2b: bool
    ) -> tuple[Decimal, Decimal]:
        if sanatorium is None:
            return _ZERO, _ZERO
        percent = (
            sanatorium.b2b_commission_percent
            if is_b2b
            else sanatorium.platform_commission_percent
        ) or _ZERO
        return percent, apply_percent(final_price, percent)

    async def _agent_tier_discount(self, user: User, sanatorium: Sanatorium) -> Decimal:
        if not sanatorium.agent_discount_tiers:
            return _ZERO
        year_start = datetime(datetime.now(UTC).year, 1, 1, tzinfo=UTC)
        count = await self.db.scalar(
            select(func.count(Booking.id)).where(
                Booking.user_id == user.id,
                Booking.is_b2b.is_(True),
                Booking.status != BookingStatus.CANCELLED,
                Booking.created_at >= year_start,
            )
        )
        return best_tier_discount_percent(
            sanatorium.agent_discount_tiers, int(count or 0)
        )


@dataclass(slots=True)
class BookingPricing:
    final_price: Decimal
    agent_discount_percent: Decimal
    commission_percent: Decimal
    commission_amount: Decimal


def get_booking_pricing_policy(
    db: AsyncSession = Depends(get_db),
) -> BookingPricingPolicy:
    return BookingPricingPolicy(db)
