import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.booking import BookingStatus, BookingType
from app.models.rate_plan import BoardType, PaymentTiming
from app.models.user import UserRole
from app.schemas.extra_bed import BookingExtraBedRead, ExtraBedItem
from app.schemas.payment import BookingPaymentSummary


class BookingCustomerRead(BaseModel):
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
    package_id: uuid.UUID | None = None
    rate_plan_id: uuid.UUID | None = None
    check_in: date
    check_out: date | None = None
    guests: int = Field(default=1, ge=1)
    extra_beds: list[ExtraBedItem] = Field(default_factory=list)
    guest_details: list[GuestDetail] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self):
        provided = sum(
            x is not None for x in (self.room_id, self.program_id, self.package_id)
        )
        if provided != 1:
            raise ValueError(
                "Provide exactly one of room_id, program_id, or package_id"
            )
        if self.rate_plan_id is not None and self.room_id is None:
            raise ValueError("rate_plan_id is only valid with a room booking")
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
    package_id: uuid.UUID | None
    rate_plan_id: uuid.UUID | None = None
    booking_type: BookingType
    check_in: date
    check_out: date
    guests: int
    rooms_count: int
    status: BookingStatus
    final_price: Decimal
    original_price: Decimal | None = None
    promo_percent_snapshot: Decimal | None = None
    currency: str
    board: BoardType | None = None
    refundable: bool | None = None
    free_cancellation_days: int | None = None
    cancellation_penalty_percent: Decimal | None = None
    cancellation_penalty_amount: Decimal | None = None
    payment_timing: PaymentTiming | None = None
    is_b2b: bool
    guest_details: list[GuestDetail] = Field(default_factory=list)
    extra_beds: list[BookingExtraBedRead] = []
    payments: list[BookingPaymentSummary] = Field(default_factory=list)
    customer: BookingCustomerRead | None = None
    created_at: datetime
    updated_at: datetime


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
