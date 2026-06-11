import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ExchangeRateUpsert(BaseModel):
    pair: str = Field(pattern=r"^[A-Z]{3}_[A-Z]{3}$")
    rate: Decimal = Field(gt=0, decimal_places=6)
    valid_from: datetime


class ExchangeRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    rate: Decimal
    source: str
    valid_from: datetime
    created_at: datetime


class ExchangeRateCurrency(BaseModel):
    currency: str
    rate_to_uzs: Decimal | None
    source: str | None
    valid_from: datetime | None
    is_available: bool


class ExchangeRateCurrencyList(BaseModel):
    default_currency: str
    currencies: list[ExchangeRateCurrency]
