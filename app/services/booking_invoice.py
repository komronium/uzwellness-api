from datetime import UTC, datetime
from decimal import Decimal

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.models.booking import Booking
from app.models.user import User


class BookingInvoiceBuilder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(self, booking: Booking) -> dict:
        sanatorium_name = await sanatorium_name_for_booking(self.db, booking) or ""
        user = (
            await self.db.get(User, booking.user_id) if booking.user_id else None
        )
        nights = max((booking.check_out - booking.check_in).days, 1)
        total = booking.final_price
        extras_total = sum((eb.total_price for eb in booking.extra_beds), Decimal("0"))
        rooms_subtotal = total - extras_total
        line_items: list[dict] = [
            {
                "description": "Room/program",
                "qty": booking.guests,
                "amount": rooms_subtotal,
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
            "subtotal": rooms_subtotal,
            "total": total,
            "currency": booking.currency,
            "is_b2b": booking.is_b2b,
            "line_items": line_items,
        }


def get_booking_invoice_builder(
    db: AsyncSession = Depends(get_db),
) -> BookingInvoiceBuilder:
    return BookingInvoiceBuilder(db)
