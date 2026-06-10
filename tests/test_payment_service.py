from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.payment_gateways import WebhookResult
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.services.payment_service import PaymentService
from tests.factories import make_room, make_sanatorium, make_user


async def _booking_with_payment(
    db: AsyncSession, *, payment_status: PaymentStatus = PaymentStatus.PENDING
) -> tuple[Booking, Payment]:
    user = await make_user(db, email="payer@test.com")
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)
    booking = Booking(
        user_id=user.id,
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
    await db.flush()
    payment = Payment(
        booking_id=booking.id,
        method=PaymentMethod.CLICK,
        amount=Decimal("100.00"),
        currency="USD",
        merchant_trans_id="trans-1",
        status=payment_status,
    )
    db.add(payment)
    await db.commit()
    return booking, payment


def _paid_result(amount: Decimal | None) -> WebhookResult:
    return WebhookResult(
        merchant_trans_id="trans-1",
        provider_payment_id="prov-1",
        is_paid=True,
        is_failed=False,
        amount=amount,
    )


async def test_webhook_amount_mismatch_is_rejected(db: AsyncSession):
    _, payment = await _booking_with_payment(db)
    service = PaymentService(db)

    with pytest.raises(HTTPException) as exc:
        await service._apply_webhook_result(payment, _paid_result(Decimal("1.00")), {})

    assert exc.value.status_code == 400
    assert payment.status == PaymentStatus.PENDING


async def test_webhook_matching_amount_marks_paid(db: AsyncSession):
    booking, payment = await _booking_with_payment(db)
    service = PaymentService(db)

    await service._apply_webhook_result(payment, _paid_result(Decimal("100.00")), {})

    assert payment.status == PaymentStatus.PAID
    assert booking.status == BookingStatus.CONFIRMED


async def test_cancel_webhook_after_paid_marks_refunded(db: AsyncSession):
    _, payment = await _booking_with_payment(db, payment_status=PaymentStatus.PAID)
    service = PaymentService(db)

    result = WebhookResult(
        merchant_trans_id="trans-1",
        provider_payment_id="prov-1",
        is_paid=False,
        is_failed=True,
    )
    await service._apply_webhook_result(payment, result, {})

    assert payment.status == PaymentStatus.REFUNDED


async def test_cancel_webhook_before_paid_marks_failed(db: AsyncSession):
    _, payment = await _booking_with_payment(db)
    service = PaymentService(db)

    result = WebhookResult(
        merchant_trans_id="trans-1",
        provider_payment_id=None,
        is_paid=False,
        is_failed=True,
    )
    await service._apply_webhook_result(payment, result, {})

    assert payment.status == PaymentStatus.FAILED


async def test_initiate_rejected_when_already_paid(db: AsyncSession):
    booking, payment = await _booking_with_payment(
        db, payment_status=PaymentStatus.PAID
    )
    user = await db.get(type(payment), payment.id)  # ensure session is live
    owner = await make_user(db, email="owner2@test.com")
    booking.user_id = owner.id
    await db.commit()
    service = PaymentService(db)

    with pytest.raises(HTTPException) as exc:
        await service.initiate(booking.id, PaymentMethod.CLICK, owner)

    assert exc.value.status_code == 409
    assert "already paid" in exc.value.detail.lower()
