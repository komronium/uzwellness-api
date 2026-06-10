import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models.booking import BookingStatus, BookingType
from app.schemas.common import Page

PaymentRollupStatus = Literal[
    "unpaid",
    "pending",
    "partially_paid",
    "paid",
    "refund_pending",
    "refunded",
]


class FinanceCurrencyTotals(BaseModel):
    currency: str
    booking_count: int
    cancelled_bookings: int
    b2b_bookings: int
    b2c_bookings: int
    gross_amount: Decimal
    cancelled_gross_amount: Decimal
    paid_amount: Decimal
    pending_payment_amount: Decimal
    refund_pending_amount: Decimal
    refunded_amount: Decimal
    platform_commission_amount: Decimal | None = None
    sanatorium_net_amount: Decimal | None = None


class FinanceSummary(BaseModel):
    items: list[FinanceCurrencyTotals]


class FinanceOrderItem(BaseModel):
    booking_id: uuid.UUID
    booking_code: str
    booking_type: BookingType
    booking_status: BookingStatus
    payment_status: PaymentRollupStatus
    sanatorium_id: uuid.UUID | None
    sanatorium_name: str | None
    agent_id: uuid.UUID | None
    agent_email: str | None
    agent_name: str | None
    is_b2b: bool
    gross_amount: Decimal
    paid_amount: Decimal
    pending_payment_amount: Decimal
    refund_pending_amount: Decimal
    refunded_amount: Decimal
    commission_percent: Decimal | None = None
    platform_commission_amount: Decimal | None = None
    sanatorium_net_amount: Decimal | None = None
    agent_discount_percent: Decimal | None = None
    currency: str
    check_in: date
    created_at: datetime


class FinanceOrdersList(Page[FinanceOrderItem]):
    pass
