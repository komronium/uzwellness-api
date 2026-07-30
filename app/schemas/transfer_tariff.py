import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.transfer_request import VehicleType
from app.schemas.common import Page


class TransferTariffCreate(BaseModel):
    route_from_id: uuid.UUID
    route_to_id: uuid.UUID
    vehicle_type: VehicleType
    price: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^(UZS|USD)$")

    @model_validator(mode="after")
    def _validate(self):
        if self.route_from_id == self.route_to_id:
            raise ValueError("route_from_id and route_to_id must differ")
        return self


class TransferTariffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    route_from_id: uuid.UUID
    route_to_id: uuid.UUID
    vehicle_type: VehicleType
    price: Decimal
    currency: str
    display_price: Decimal | None = None
    display_currency: str | None = None
    effective_from: datetime
    effective_to: datetime | None
    is_current: bool


class TransferTariffList(Page[TransferTariffRead]):
    pass
