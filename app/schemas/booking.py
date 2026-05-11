import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    room_category_id: uuid.UUID
    check_in: date
    check_out: date
    guests: int = Field(default=1, ge=1)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    user_id: uuid.UUID | None
    room_category_id: uuid.UUID | None
    check_in: date
    check_out: date
    guests: int
    status: BookingStatus
    final_price: Decimal
    currency: str
    created_at: datetime


class BookingList(BaseModel):
    items: list[BookingRead]
    total: int
    limit: int
    offset: int
