import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.transfer_request import VehicleType
from app.schemas.common import Page


class TransferVehicleCreate(BaseModel):
    vehicle_type: VehicleType
    capacity: int = Field(ge=1, le=80)
    plate: str = Field(min_length=1, max_length=32)
    label: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class TransferVehicleUpdate(BaseModel):
    vehicle_type: VehicleType | None = None
    capacity: int | None = Field(default=None, ge=1, le=80)
    plate: str | None = Field(default=None, min_length=1, max_length=32)
    label: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class TransferVehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_type: VehicleType
    capacity: int
    plate: str
    label: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TransferVehicleList(Page[TransferVehicleRead]):
    pass
