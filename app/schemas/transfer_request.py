import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Page
from app.models.transfer_request import (
    TransferDirection,
    TransferStatus,
    VehicleType,
)


class TransferRequestCreate(BaseModel):
    booking_id: uuid.UUID | None = None
    direction: TransferDirection
    pickup_location: str = Field(min_length=1, max_length=255)
    dropoff_location: str = Field(min_length=1, max_length=255)
    flight_number: str | None = Field(default=None, max_length=20)
    flight_time: datetime | None = None
    return_flight_number: str | None = Field(default=None, max_length=20)
    return_flight_time: datetime | None = None
    passengers_count: int = Field(default=1, ge=1, le=50)
    vehicle_type: VehicleType = VehicleType.SEDAN
    notes: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _validate(self):
        if (
            self.direction
            in (
                TransferDirection.ARRIVAL,
                TransferDirection.ROUND_TRIP,
            )
            and self.flight_time is None
        ):
            raise ValueError(
                "flight_time is required for arrival and round_trip transfers"
            )
        if self.direction == TransferDirection.ROUND_TRIP:
            if self.return_flight_time is None:
                raise ValueError(
                    "return_flight_time is required for round_trip transfers"
                )
            if (
                self.flight_time is not None
                and self.return_flight_time <= self.flight_time
            ):
                raise ValueError("return_flight_time must be after flight_time")
        if (
            self.direction != TransferDirection.ROUND_TRIP
            and self.return_flight_time is not None
        ):
            raise ValueError(
                "return_flight_time is only allowed for round_trip transfers"
            )
        return self


class TransferRequestUpdate(BaseModel):
    status: TransferStatus | None = None
    vehicle_type: VehicleType | None = None
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    driver_name: str | None = Field(default=None, max_length=255)
    driver_phone: str | None = Field(default=None, max_length=32)
    admin_notes: str | None = Field(default=None, max_length=2000)


class TransferRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    booking_id: uuid.UUID | None
    direction: TransferDirection
    pickup_location: str
    dropoff_location: str
    flight_number: str | None
    flight_time: datetime | None
    return_flight_number: str | None
    return_flight_time: datetime | None
    passengers_count: int
    vehicle_type: VehicleType
    price: Decimal | None
    currency: str | None
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
