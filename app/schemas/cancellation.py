import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.cancellation import CancellationStatus


class CancellationConfirm(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class CancellationRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    status: CancellationStatus
    expires_at: datetime
    created_at: datetime
