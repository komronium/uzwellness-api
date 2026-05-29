from datetime import date

from pydantic import BaseModel, Field


class AvailabilityBlock(BaseModel):
    date_from: date
    date_to: date
    units_blocked: int = Field(ge=0, description="Units to mark blocked per day")


class AvailabilityUpsert(BaseModel):
    units_blocked: int = Field(ge=0)


class AvailabilityRead(BaseModel):
    date: date
    inventory_count: int
    units_blocked: int
    units_booked: int
    units_available: int
