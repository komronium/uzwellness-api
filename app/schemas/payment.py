from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentInitiateRequest(BaseModel):
    booking_id: uuid.UUID
    method: PaymentMethod


class PaymentInitiateResponse(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus
    redirect_url: str | None = None


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
