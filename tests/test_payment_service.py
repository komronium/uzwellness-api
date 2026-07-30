"""Cash payment flow. Uzum lives in tests/test_uzum_merchant.py."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.services.payment_service import PaymentService
from tests.factories import make_room, make_sanatorium, make_user


async def _booking(db: AsyncSession, owner: User) -> Booking:
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)
    booking = Booking(
        user_id=owner.id,
        room_id=room.id,
        booking_type=BookingType.ROOM,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guests=1,
        status=BookingStatus.CONFIRMED,
        final_price=Decimal("100.00"),
        currency="USD",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def test_initiate_cash_creates_pending_payment(db: AsyncSession):
    owner = await make_user(db, email="cash-payer@test.com")
    booking = await _booking(db, owner)

    payment = await PaymentService(db).initiate(booking.id, PaymentMethod.CASH, owner)

    assert payment.status == PaymentStatus.PENDING
    assert payment.merchant_trans_id == booking.reservation_number
    assert booking.status == BookingStatus.PENDING


async def test_initiate_uzum_is_rejected(db: AsyncSession):
    owner = await make_user(db, email="uzum-payer@test.com")
    booking = await _booking(db, owner)

    with pytest.raises(HTTPException) as exc:
        await PaymentService(db).initiate(booking.id, PaymentMethod.UZUM, owner)

    assert exc.value.status_code == 400
    assert "Uzum Bank app" in exc.value.detail


async def test_initiate_rejected_when_already_paid(db: AsyncSession):
    owner = await make_user(db, email="owner2@test.com")
    booking = await _booking(db, owner)
    db.add(
        Payment(
            booking_id=booking.id,
            method=PaymentMethod.UZUM,
            status=PaymentStatus.PAID,
            amount=Decimal("100.00"),
            currency="USD",
        )
    )
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await PaymentService(db).initiate(booking.id, PaymentMethod.CASH, owner)

    assert exc.value.status_code == 409
    assert "already paid" in exc.value.detail.lower()


async def test_initiate_rejected_for_other_users_booking(db: AsyncSession):
    owner = await make_user(db, email="owner3@test.com")
    intruder = await make_user(db, email="intruder@test.com")
    booking = await _booking(db, owner)

    with pytest.raises(HTTPException) as exc:
        await PaymentService(db).initiate(booking.id, PaymentMethod.CASH, intruder)

    assert exc.value.status_code == 403


async def test_confirm_cash_marks_paid_and_confirms_booking(db: AsyncSession):
    owner = await make_user(db, email="cash-owner@test.com")
    admin = await make_user(db, email="cash-admin@test.com", role=UserRole.ADMIN)
    booking = await _booking(db, owner)
    payment = await PaymentService(db).initiate(booking.id, PaymentMethod.CASH, owner)

    confirmed = await PaymentService(db).confirm_cash(payment.id, admin)

    assert confirmed.status == PaymentStatus.PAID
    assert confirmed.paid_at is not None
    await db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED


async def test_confirm_cash_requires_staff(db: AsyncSession):
    owner = await make_user(db, email="cash-owner2@test.com")
    booking = await _booking(db, owner)
    payment = await PaymentService(db).initiate(booking.id, PaymentMethod.CASH, owner)

    with pytest.raises(HTTPException) as exc:
        await PaymentService(db).confirm_cash(payment.id, owner)

    assert exc.value.status_code == 403
