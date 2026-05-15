from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class B2BDashboard(BaseModel):
    total_bookings: int
    bookings_this_month: int
    total_spent: Decimal
    total_commission: Decimal


class B2BClient(BaseModel):
    booking_id: str
    booking_code: str
    check_in: date
    check_out: date
    full_name: str
    passport: str | None = None
    country: str | None = None


class B2BClientList(BaseModel):
    items: list[B2BClient]
    total: int
    limit: int
    offset: int
