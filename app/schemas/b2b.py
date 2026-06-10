import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.booking import BookingStatus
from app.schemas.common import Page


class B2BDashboard(BaseModel):
    total_bookings: int
    bookings_this_month: int
    bookings_this_year: int
    total_paid: Decimal
    current_year_bookings: int


class B2BDiscountNextTier(BaseModel):
    min_bookings: int
    discount_percent: Decimal
    bookings_to_unlock: int


class B2BDiscountStatus(BaseModel):
    sanatorium_id: uuid.UUID
    current_year_bookings: int
    current_tier_discount_percent: Decimal
    next_tier: B2BDiscountNextTier | None = None


class B2BOrderItem(BaseModel):
    booking_id: uuid.UUID
    booking_code: str
    sanatorium_name: str | None
    price_paid: Decimal
    agent_discount_percent: Decimal | None
    currency: str
    check_in: date
    check_out: date
    status: BookingStatus
    created_at: datetime


class B2BOrdersList(Page[B2BOrderItem]):
    pass
