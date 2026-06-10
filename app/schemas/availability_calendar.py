import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming


class AvailabilityCalendarRatePlanDay(BaseModel):
    date: date
    is_sellable: bool
    is_closed: bool
    selling_rate: Decimal
    currency: str
    min_advance_hours: int | None = None
    max_advance_hours: int | None = None
    min_stay_nights: int | None = None
    min_stay_arrival_nights: int | None = None


class AvailabilityCalendarRatePlan(BaseModel):
    id: uuid.UUID
    name: dict
    board: BoardType
    payment_timing: PaymentTiming
    confirmation: ConfirmationType
    board_guests: int | None
    days: list[AvailabilityCalendarRatePlanDay]


class AvailabilityCalendarRoomDay(BaseModel):
    date: date
    room_status: Literal["bookable", "unbookable"]
    inventory_count: int
    units_available: int
    units_booked: int
    units_blocked: int


class AvailabilityCalendarRoom(BaseModel):
    id: uuid.UUID
    name: dict
    capacity: int
    inventory_count: int
    is_active: bool
    days: list[AvailabilityCalendarRoomDay]
    rate_plans: list[AvailabilityCalendarRatePlan]


class AvailabilityCalendarRead(BaseModel):
    date_from: date
    date_to: date
    rooms: list[AvailabilityCalendarRoom]


class AvailableAllotmentSet(BaseModel):
    date_from: date
    date_to: date
    units_available: int = Field(ge=0)


class PublicAvailabilityDay(BaseModel):
    available: bool
    rooms_left: int | None = None


class PublicMonthAvailability(BaseModel):
    dates: dict[str, PublicAvailabilityDay]
