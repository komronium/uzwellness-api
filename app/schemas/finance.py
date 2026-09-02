import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from app.models.booking import BookingStatus, BookingType
from app.schemas.common import Page


class FinancePaymentStatus(StrEnum):
    """Derived payment state of a booking (payments vs. amount due).

    Not a stored column — computed in ``finance_rules.payment_status`` and the
    matching SQL in ``finance_rules.payment_status_expr``.
    """

    UNPAID = "unpaid"
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"


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
    # Settled payments in a currency other than the booking's — Uzum only
    # settles in UZS, so a non-UZS stay paid by card lands here instead of in
    # paid_amount, which is denominated in the booking's own currency.
    foreign_payment_count: int = 0
    platform_commission_amount: Decimal | None = None
    sanatorium_net_amount: Decimal | None = None


class FinanceSummary(BaseModel):
    items: list[FinanceCurrencyTotals]


class FinanceOrderItem(BaseModel):
    booking_id: uuid.UUID
    booking_code: str
    booking_type: BookingType
    booking_status: BookingStatus
    payment_status: FinancePaymentStatus
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
    # Settled payments in a currency other than the booking's — Uzum only
    # settles in UZS, so a non-UZS stay paid by card lands here instead of in
    # paid_amount, which is denominated in the booking's own currency.
    foreign_payment_count: int = 0
    commission_percent: Decimal | None = None
    platform_commission_amount: Decimal | None = None
    sanatorium_net_amount: Decimal | None = None
    agent_discount_percent: Decimal | None = None
    currency: str
    check_in: date
    created_at: datetime


class FinanceOrdersList(Page[FinanceOrderItem]):
    pass
