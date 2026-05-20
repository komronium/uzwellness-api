import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.visa_request import VisaPurpose, VisaStatus


class VisaRequestCreate(BaseModel):
    booking_id: uuid.UUID | None = None
    full_name: str = Field(min_length=1, max_length=255)
    citizenship: str = Field(min_length=2, max_length=120)
    passport_number: str = Field(min_length=2, max_length=64)
    date_of_birth: date
    arrival_date: date
    departure_date: date
    purpose: VisaPurpose = VisaPurpose.TOURISM
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _validate_dates(self):
        if self.departure_date < self.arrival_date:
            raise ValueError("departure_date must be on or after arrival_date")
        if self.date_of_birth >= self.arrival_date:
            raise ValueError("date_of_birth must be before arrival_date")
        return self


class VisaStatusUpdate(BaseModel):
    status: VisaStatus
    admin_notes: str | None = Field(default=None, max_length=2000)


class VisaRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    booking_id: uuid.UUID | None
    full_name: str
    citizenship: str
    passport_number: str
    date_of_birth: date
    arrival_date: date
    departure_date: date
    purpose: VisaPurpose
    passport_scan_url: str | None
    issued_document_url: str | None
    status: VisaStatus
    admin_notes: str | None
    contact_email: str | None
    contact_phone: str | None
    created_at: datetime
    updated_at: datetime


class VisaRequestList(BaseModel):
    items: list[VisaRequestRead]
    total: int
    limit: int
    offset: int
