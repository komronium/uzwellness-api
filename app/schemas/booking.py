import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.booking import BookingStatus, BookingType
from app.models.user import UserRole
from app.schemas.extra_bed import BookingExtraBedRead, ExtraBedItem


class BookingCustomerRead(BaseModel):
    """User info exposed to admin/super_admin viewers on bookings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    phone: str | None = None
    role: UserRole


class GuestDetail(BaseModel):
    full_name: str = Field(max_length=255)
    passport: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=60)


class BookingCreate(BaseModel):
    room_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    check_in: date
    check_out: date | None = None
    guests: int = Field(default=1, ge=1)
    extra_beds: list[ExtraBedItem] = Field(default_factory=list)
    guest_details: list[GuestDetail] = Field(default_factory=list)
    b2b_client_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    @model_validator(mode="after")
    def _validate(self):
        if (self.room_id is None) == (self.program_id is None):
            raise ValueError("Provide exactly one of room_id or program_id")
        if self.guest_details and len(self.guest_details) > self.guests:
            raise ValueError("guest_details cannot exceed guests count")
        return self


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    user_id: uuid.UUID | None
    room_id: uuid.UUID | None
    program_id: uuid.UUID | None
    booking_type: BookingType
    check_in: date
    check_out: date
    guests: int
    rooms_count: int
    status: BookingStatus
    final_price: Decimal
    currency: str
    is_b2b: bool
    b2b_client_price: Decimal | None = None
    b2b_commission: Decimal | None = None
    guest_details: list[GuestDetail] = Field(default_factory=list)
    extra_beds: list[BookingExtraBedRead] = []
    customer: BookingCustomerRead | None = None
    created_at: datetime


class BookingList(BaseModel):
    items: list[BookingRead]
    total: int
    limit: int
    offset: int


class InvoiceRead(BaseModel):
    booking_code: str
    issued_at: datetime
    customer_name: str
    customer_email: str | None
    sanatorium_name: str
    check_in: date
    check_out: date
    nights: int
    guests: int
    subtotal: Decimal
    total: Decimal
    currency: str
    is_b2b: bool
    line_items: list[dict]
