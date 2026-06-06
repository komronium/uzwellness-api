import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.rate_plan import BoardType
from app.models.stay_option import StayOptionGuestType


class StayOptionPriceBase(BaseModel):
    guest_type: StayOptionGuestType
    board: BoardType
    treatment_included: bool
    price_delta: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="UZS", min_length=3, max_length=3)
    is_available: bool = True

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class StayOptionPriceUpsert(StayOptionPriceBase):
    pass


class StayOptionPriceRead(StayOptionPriceBase):
    id: uuid.UUID
    sanatorium_id: uuid.UUID

    model_config = {"from_attributes": True}


class StayOptionPriceList(BaseModel):
    items: list[StayOptionPriceRead]


class StayOptionPriceBulkUpdate(BaseModel):
    items: list[StayOptionPriceUpsert] = Field(min_length=1, max_length=40)
