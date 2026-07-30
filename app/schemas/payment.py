import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentInitiateRequest(BaseModel):
    booking_id: uuid.UUID
    method: PaymentMethod


class PaymentInitiateResponse(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus


class UzumOrderInfo(BaseModel):
    """What the guest types into the Uzum Bank app to pay for a booking."""

    booking_id: uuid.UUID
    order_id: str
    service_id: int
    amount: Decimal
    currency: str


class BookingPaymentSummary(BaseModel):
    """Payment fields embedded in a booking detail/list response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    method: PaymentMethod
    status: PaymentStatus
    amount: Decimal
    currency: str
    created_at: datetime
    paid_at: datetime | None
