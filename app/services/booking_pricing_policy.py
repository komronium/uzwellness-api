from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discount_tiers import best_tier_discount_percent
from app.models.booking import Booking, BookingStatus
from app.models.sanatorium import Sanatorium
from app.models.user import User
from app.schemas.booking import BookingCreate

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
        payload: BookingCreate,
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
        b2b_client_price = self._resolve_b2b_client_price(payload, is_b2b, discounted)
        commission_percent, commission_amount = self._commission_snapshot(
            sanatorium, discounted, is_b2b
        )
        return BookingPricing(
            final_price=discounted,
            agent_discount_percent=agent_discount_percent,
            b2b_client_price=b2b_client_price,
            commission_percent=commission_percent,
            commission_amount=commission_amount,
        )

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


@dataclass(slots=True)
class BookingPricing:
    final_price: Decimal
    agent_discount_percent: Decimal
    b2b_client_price: Decimal | None
    commission_percent: Decimal
    commission_amount: Decimal
