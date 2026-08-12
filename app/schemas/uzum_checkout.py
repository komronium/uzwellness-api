"""Wire schemas for Uzum Checkout's merchant callbacks.

Field names are camelCase and fixed by Uzum's specification (Checkout 1.10.3),
so each carries an explicit alias.

Every field is optional on purpose. A callback that fails to match the spec
must still be stored and acknowledged — losing a payment notification because
Uzum added a field is far worse than recording one with gaps. The typed model
is a best-effort read of a payload that is always kept verbatim alongside it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentStatus


class _CallbackModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class AcquiringCallback(_CallbackModel):
    """Result of a financial operation — the callback that moves money."""

    order_id: str | None = Field(default=None, alias="orderId")
    order_number: str | None = Field(default=None, alias="orderNumber")
    # SUCCESS | FAIL
    operation_state: str | None = Field(default=None, alias="operationState")
    # AUTHORIZE | COMPLETE | REFUND | REVERSE | TOP_UP_COMPLETED
    operation_type: str | None = Field(default=None, alias="operationType")
    merchant_operation_id: str | None = Field(default=None, alias="merchantOperationId")
    card_type: int | None = Field(default=None, alias="cardType")
    rrn: str | None = None


class BusinessEventCallback(_CallbackModel):
    """Business event — currently only ``FORM_CLOSED``."""

    order_id: str | None = Field(default=None, alias="orderId")
    order_number: str | None = Field(default=None, alias="orderNumber")
    event_type: str | None = Field(default=None, alias="eventType")
    action_code: int | None = Field(default=None, alias="actionCode")
    action_code_description: str | None = Field(
        default=None, alias="actionCodeDescription"
    )


class ReceiptCallback(_CallbackModel):
    """A fiscal receipt was generated for an order."""

    order_id: str | None = Field(default=None, alias="orderId")
    # PURCHASE | PREPAID | REFUND
    receipt_type: str | None = Field(default=None, alias="receiptType")
    receipt_url: str | None = Field(default=None, alias="receiptUrl")


class CheckoutStartRequest(BaseModel):
    """Ask Uzum to open a card payment for a booking."""

    booking_id: uuid.UUID
    # Language of Uzum's payment form; falls back to the request locale.
    locale: str | None = Field(default=None, pattern="^(uz|ru|en)$")


class CheckoutSessionRead(BaseModel):
    """What the frontend needs to send the guest to Uzum's payment page."""

    payment_id: uuid.UUID
    booking_id: uuid.UUID
    order_id: str
    order_number: str
    payment_url: str
    amount: Decimal  # UZS, whole so'm — what the guest is charged
    currency: str = "UZS"
    status: PaymentStatus


class CheckoutPaymentStatusRead(BaseModel):
    """Current state of a Checkout payment, refreshed from Uzum."""

    payment_id: uuid.UUID
    booking_id: uuid.UUID
    order_id: str | None
    status: PaymentStatus
    # Uzum's own order state (REGISTERED / COMPLETED / DECLINED / REFUNDED);
    # None when Uzum could not be reached and the local state is being shown.
    order_status: str | None = None
    amount: Decimal
    currency: str
