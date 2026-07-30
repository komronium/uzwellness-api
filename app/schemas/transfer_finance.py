import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.transfer_request import (
    TransferDirection,
    TransferPaymentState,
    TransferStatus,
    VehicleType,
)
from app.schemas.common import Page


class TransferFinanceCurrencyTotals(BaseModel):
    currency: str
    order_count: int
    gross_amount: Decimal
    # Null when the rows in this currency were priced under different
    # commission percentages — the amount stays exact either way.
    platform_commission_percent: Decimal | None = None
    platform_commission_amount: Decimal
    net_payout_amount: Decimal
    unpaid_amount: Decimal


class TransferFinanceSummary(BaseModel):
    items: list[TransferFinanceCurrencyTotals]


class TransferFinanceOrderItem(BaseModel):
    transfer_id: uuid.UUID
    booking_id: uuid.UUID | None
    booking_code: str | None
    direction: TransferDirection
    vehicle_type: VehicleType
    pickup_location: str
    dropoff_location: str
    status: TransferStatus
    payment_state: TransferPaymentState
    gross_amount: Decimal
    platform_commission_percent: Decimal | None
    platform_commission_amount: Decimal
    net_payout_amount: Decimal
    currency: str
    created_at: datetime


class TransferFinanceOrdersList(Page[TransferFinanceOrderItem]):
    pass
