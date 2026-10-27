"""Delete bookings created before a cutoff date (and their payments).

Bookings that carry real money movement (a payment that is paid, refund_pending
or refunded) are kept unless --include-paid is passed, so the finance trail with
Uzum stays intact by default.

Usage:
    uv run python -m scripts.delete_old_bookings --before 2026-10-01
    uv run python -m scripts.delete_old_bookings --before 2026-10-01 --write --confirm-delete-bookings

Without --write the script only reports what it would delete and rolls back.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete, exists, func, select

from app.core.database import SessionLocal
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentStatus

_TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
_MONEY_STATUSES = (
    PaymentStatus.PAID,
    PaymentStatus.REFUND_PENDING,
    PaymentStatus.REFUNDED,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before",
        type=date.fromisoformat,
        required=True,
        help="Delete bookings created before this date (YYYY-MM-DD, Tashkent time).",
    )
    parser.add_argument(
        "--include-paid",
        action="store_true",
        help="Also delete bookings with paid/refund_pending/refunded payments.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist changes. Without this flag the script rolls back.",
    )
    parser.add_argument(
        "--confirm-delete-bookings",
        action="store_true",
        help="Required with --write because deleted bookings cannot be restored.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    cutoff = datetime.combine(args.before, time.min, tzinfo=_TASHKENT_TZ)
    has_money = exists().where(
        Payment.booking_id == Booking.id, Payment.status.in_(_MONEY_STATUSES)
    )
    doomed = Booking.created_at < cutoff
    if not args.include_paid:
        doomed &= ~has_money

    async with SessionLocal() as db:
        total = await db.scalar(select(func.count()).select_from(Booking))
        to_delete = await db.scalar(
            select(func.count()).select_from(Booking).where(doomed)
        )
        holding = (
            await db.scalars(
                select(Booking).where(
                    doomed,
                    Booking.booking_type.in_([BookingType.ROOM, BookingType.PACKAGE]),
                    Booking.room_id.is_not(None),
                    Booking.status.in_(
                        [BookingStatus.PENDING, BookingStatus.CONFIRMED]
                    ),
                    Booking.check_out >= date.today(),
                )
            )
        ).all()

        print(f"Bookings total: {total}, to delete: {to_delete}")
        print(f"Bookings kept: {(total or 0) - (to_delete or 0)}")
        print(f"Bookings whose held room availability is released: {len(holding)}")

        if args.write and not args.confirm_delete_bookings:
            raise SystemExit("Refusing to write. Pass --confirm-delete-bookings.")

        # Same release as BookingService.cancel(): free the units the booking holds.
        for booking in holding:
            rows = await db.scalars(
                select(RoomAvailability)
                .where(
                    RoomAvailability.room_id == booking.room_id,
                    RoomAvailability.date >= booking.check_in,
                    RoomAvailability.date < booking.check_out,
                )
                .with_for_update()
            )
            for row in rows:
                row.units_booked = max(row.units_booked - booking.rooms_count, 0)
        await db.flush()

        # payments.booking_id is ON DELETE RESTRICT, so they go first.
        doomed_ids = select(Booking.id).where(doomed)
        await db.execute(delete(Payment).where(Payment.booking_id.in_(doomed_ids)))
        await db.execute(delete(Booking).where(doomed))

        if args.write:
            await db.commit()
            print("Deleted.")
        else:
            await db.rollback()
            print("Dry run complete; rolled back.")


if __name__ == "__main__":
    asyncio.run(main())
