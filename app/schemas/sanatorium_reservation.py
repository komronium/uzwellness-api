from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReservationFallbackProcessingMethod(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    SMS = "sms"


class SanatoriumReservationSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_auto_confirmation_enabled: bool
    reservation_fallback_processing_method: ReservationFallbackProcessingMethod
    reservation_fallback_contact_name: str | None = None
    reservation_fallback_contact: str | None = None


class SanatoriumReservationSettingsUpdate(BaseModel):
    reservation_auto_confirmation_enabled: bool | None = None
    reservation_fallback_processing_method: (
        ReservationFallbackProcessingMethod | None
    ) = None
    reservation_fallback_contact_name: str | None = Field(default=None, max_length=120)
    reservation_fallback_contact: str | None = Field(default=None, max_length=255)
