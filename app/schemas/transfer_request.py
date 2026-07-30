import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.transfer_request import (
    TransferDirection,
    TransferPaymentState,
    TransferStatus,
    VehicleType,
)
from app.schemas.common import Page


def validate_flight_fields(
    *,
    direction: TransferDirection,
    flight_time: datetime | None,
    return_flight_time: datetime | None,
) -> None:
    """Flight-detail rules shared by standalone and in-booking transfers."""
    if (
        direction in (TransferDirection.ARRIVAL, TransferDirection.ROUND_TRIP)
        and flight_time is None
    ):
        raise ValueError("flight_time is required for arrival and round_trip transfers")
    if direction == TransferDirection.ROUND_TRIP:
        if return_flight_time is None:
            raise ValueError("return_flight_time is required for round_trip transfers")
        if flight_time is not None and return_flight_time <= flight_time:
            raise ValueError("return_flight_time must be after flight_time")
    elif return_flight_time is not None:
        raise ValueError("return_flight_time is only allowed for round_trip transfers")


class TransferDetailsBase(BaseModel):
    """Guest-supplied details, identical for both ways of ordering a transfer."""

    direction: TransferDirection
    flight_number: str | None = Field(default=None, max_length=20)
    flight_time: datetime | None = None
    return_flight_number: str | None = Field(default=None, max_length=20)
    return_flight_time: datetime | None = None
    passengers_count: int = Field(default=1, ge=1, le=50)
    notes: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _validate_flights(self):
        validate_flight_fields(
            direction=self.direction,
            flight_time=self.flight_time,
            return_flight_time=self.return_flight_time,
        )
        return self


class BookingTransferCreate(TransferDetailsBase):
    """Transfer add-on submitted inside booking checkout.

    The client never sends a price — the backend resolves the tariff that is
    current at submit time and folds it into the booking total.
    """

    route_from_id: uuid.UUID
    route_to_id: uuid.UUID
    vehicle_type: VehicleType

    @model_validator(mode="after")
    def _validate_route(self):
        if self.route_from_id == self.route_to_id:
            raise ValueError("route_from_id and route_to_id must differ")
        return self


class TransferRequestCreate(TransferDetailsBase):
    """Standalone transfer order, placed after (or without) a booking.

    Supply ``route_from_id``/``route_to_id`` to have it priced from the tariff
    table; supply the free-text locations instead for an off-tariff job the
    operator will price by hand.
    """

    booking_id: uuid.UUID | None = None
    route_from_id: uuid.UUID | None = None
    route_to_id: uuid.UUID | None = None
    vehicle_type: VehicleType = VehicleType.SEDAN
    pickup_location: str | None = Field(default=None, min_length=1, max_length=255)
    dropoff_location: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def _validate_route(self):
        routed = (self.route_from_id is not None, self.route_to_id is not None)
        if any(routed) and not all(routed):
            raise ValueError("route_from_id and route_to_id must be given together")
        if all(routed) and self.route_from_id == self.route_to_id:
            raise ValueError("route_from_id and route_to_id must differ")
        if not any(routed) and not (self.pickup_location and self.dropoff_location):
            raise ValueError(
                "Provide route_from_id and route_to_id, or "
                "pickup_location and dropoff_location"
            )
        return self


#: Fields a guest may change on their own transfer. Everything else on
#: ``TransferRequestUpdate`` is operator-only and rejected with 403.
CUSTOMER_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "flight_number",
        "flight_time",
        "return_flight_number",
        "return_flight_time",
        "notes",
        "contact_phone",
    }
)


class TransferRequestUpdate(BaseModel):
    """Role-split PATCH body.

    Operators (transfer_admin / super_admin) may set every field; guests are
    limited to ``CUSTOMER_EDITABLE_FIELDS``.
    """

    status: TransferStatus | None = None
    payment_state: TransferPaymentState | None = None
    vehicle_type: VehicleType | None = None
    vehicle_id: uuid.UUID | None = None
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    driver_name: str | None = Field(default=None, max_length=255)
    driver_phone: str | None = Field(default=None, max_length=32)
    admin_notes: str | None = Field(default=None, max_length=2000)

    flight_number: str | None = Field(default=None, max_length=20)
    flight_time: datetime | None = None
    return_flight_number: str | None = Field(default=None, max_length=20)
    return_flight_time: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = Field(default=None, max_length=32)


class TransferRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    booking_id: uuid.UUID | None
    direction: TransferDirection
    pickup_location: str
    dropoff_location: str
    route_from_id: uuid.UUID | None = None
    route_to_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    flight_number: str | None
    flight_time: datetime | None
    return_flight_number: str | None
    return_flight_time: datetime | None
    passengers_count: int
    vehicle_type: VehicleType
    price: Decimal | None
    currency: str | None
    applied_tariff_id: uuid.UUID | None = None
    applied_price: Decimal | None = None
    applied_currency: str | None = None
    payment_state: TransferPaymentState
    display_price: Decimal | None = None
    display_currency: str | None = None
    status: TransferStatus
    driver_name: str | None
    driver_phone: str | None
    notes: str | None
    admin_notes: str | None
    contact_phone: str | None
    created_at: datetime
    updated_at: datetime


class TransferRequestList(Page[TransferRequestRead]):
    pass
