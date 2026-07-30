"""Create a throwaway booking for Uzum Bank Merchant API testing.

Uzum's team needs a fresh, unpaid ``order_id`` for every test round (a booking
can only be paid once). This prints exactly the two values they ask for: the
order id and the amount in tiyin.

Usage:
    uv run python -m scripts.create_uzum_test_booking
    uv run python -m scripts.create_uzum_test_booking --price 25000
    uv run python -m scripts.create_uzum_test_booking --email me@example.com

The booking is deliberately placed a year out on an arbitrary active room and
never touches availability, so it cannot collide with real inventory. Delete
it with --cleanup once Uzum is done.
"""

import argparse
import asyncio
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole

TEST_EMAIL = "uzum-test@uzwellness.com"
TEST_FULL_NAME = "Uzum Test"


async def create(email: str, price: Decimal) -> int:
    async with SessionLocal() as db:
        room = await db.scalar(
            select(Room)
            .join(Sanatorium, Sanatorium.id == Room.sanatorium_id)
            .where(
                Room.is_active.is_(True),
                Sanatorium.status == SanatoriumStatus.APPROVED,
            )
            .order_by(Room.created_at.asc())
            .limit(1)
        )
        if room is None:
            print("No active room on an approved sanatorium found.", file=sys.stderr)
            return 1

        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password("uzum-test-account"),
                full_name=TEST_FULL_NAME,
                role=UserRole.CUSTOMER,
                is_active=True,
            )
            db.add(user)
            await db.flush()

        check_in = date.today() + timedelta(days=365)
        booking = Booking(
            user_id=user.id,
            room_id=room.id,
            booking_type=BookingType.ROOM,
            check_in=check_in,
            check_out=check_in + timedelta(days=1),
            guests=1,
            status=BookingStatus.PENDING,
            final_price=price,
            currency="UZS",
        )
        db.add(booking)
        await db.commit()
        await db.refresh(booking)

        tiyin = int(price * 100)
        print("Test booking created.\n")
        print(f"  booking_id : {booking.id}")
        print(f'  order_id   : "{booking.reservation_number}"')
        print(f"  amount     : {tiyin}   (tiyin, = {price} UZS)")
        print(f"  guest      : {email}")
        print(f"  dates      : {booking.check_in} → {booking.check_out}")
        return 0


async def cleanup(email: str) -> int:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No test account {email}; nothing to clean up.")
            return 0
        booking_ids = list(
            (
                await db.scalars(select(Booking.id).where(Booking.user_id == user.id))
            ).all()
        )
        if booking_ids:
            await db.execute(delete(Payment).where(Payment.booking_id.in_(booking_ids)))
            await db.execute(delete(Booking).where(Booking.id.in_(booking_ids)))
        await db.commit()
        print(f"Removed {len(booking_ids)} test booking(s) for {email}.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=TEST_EMAIL, help="guest account to use")
    parser.add_argument(
        "--price",
        type=Decimal,
        default=Decimal("10000.00"),
        help="booking total in UZS (default: 10000)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="delete every booking and payment of the test account instead",
    )
    args = parser.parse_args()

    if args.cleanup:
        return asyncio.run(cleanup(args.email))
    if args.price <= 0:
        print("--price must be positive", file=sys.stderr)
        return 1
    return asyncio.run(create(args.email, args.price))


if __name__ == "__main__":
    raise SystemExit(main())
