"""Folds an optional transfer add-on into a booking under one payment.

Every booking flow calls :func:`attach_booking_transfer` between the booking
INSERT and the flow's commit, so the transfer row, the bumped ``final_price``
and the booking itself land in a single transaction — a guest is never charged
for a transfer that failed to be recorded, or vice versa.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.transfer_request import (
    TransferPaymentState,
    TransferRequest,
    TransferStatus,
)
from app.schemas.transfer_request import BookingTransferCreate
from app.services.transfer_location_service import TransferLocationService
from app.services.transfer_pricing import price_transfer
from app.services.transfer_tariff_service import TransferTariffService


async def attach_booking_transfer(
    db: AsyncSession,
    *,
    booking: Booking,
    payload: BookingTransferCreate | None,
    locale: str = "en",
) -> TransferRequest | None:
    """Price the add-on, add it to the booking total and stage the row.

    The booking must already have an id (flush first). Nothing is committed
    here — the caller's commit closes the transaction.
    """
    if payload is None:
        return None

    tariffs = TransferTariffService(db, TransferLocationService(db))
    priced = await price_transfer(
        db,
        tariffs,
        route_from_id=payload.route_from_id,
        route_to_id=payload.route_to_id,
        vehicle_type=payload.vehicle_type,
        direction=payload.direction,
        target_currency=booking.currency,
        locale=locale,
    )

    booking.final_price = booking.final_price + priced.price

    transfer = TransferRequest(
        user_id=booking.user_id,
        booking_id=booking.id,
        direction=payload.direction,
        pickup_location=priced.pickup_location,
        dropoff_location=priced.dropoff_location,
        route_from_id=payload.route_from_id,
        route_to_id=payload.route_to_id,
        flight_number=payload.flight_number,
        flight_time=payload.flight_time,
        return_flight_number=payload.return_flight_number,
        return_flight_time=payload.return_flight_time,
        passengers_count=payload.passengers_count,
        vehicle_type=payload.vehicle_type,
        notes=payload.notes,
        contact_phone=payload.contact_phone,
        status=TransferStatus.REQUESTED,
        payment_state=TransferPaymentState.INCLUDED,
        applied_tariff_id=priced.tariff_id,
        applied_price=priced.price,
        applied_currency=priced.currency,
        commission_percent_snapshot=priced.commission_percent,
        commission_amount_snapshot=priced.commission_amount,
    )
    db.add(transfer)
    return transfer
