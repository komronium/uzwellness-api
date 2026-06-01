import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class BulkDateRange(BaseModel):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def _validate(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class BulkRatePlanScope(BaseModel):
    sanatorium_id: uuid.UUID
    date_ranges: list[BulkDateRange] = Field(min_length=1)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    rate_plan_ids: list[uuid.UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_weekdays(self):
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("weekdays must use Python weekday numbers: Monday=0")
        return self


class BulkAllotmentUpdate(BulkRatePlanScope):
    units_available: int = Field(ge=0)
    allow_overbooking: bool = False


class BulkRatesUpdate(BulkRatePlanScope):
    selling_rate: Decimal = Field(ge=0, decimal_places=2)
    weekend_selling_rate: Decimal | None = Field(default=None, ge=0, decimal_places=2)


class BulkRoomStatusUpdate(BulkRatePlanScope):
    is_closed: bool


class RestrictionField(StrEnum):
    MIN_ADVANCE_HOURS = "min_advance_hours"
    MAX_ADVANCE_HOURS = "max_advance_hours"
    MIN_STAY_NIGHTS = "min_stay_nights"
    MIN_STAY_ARRIVAL_NIGHTS = "min_stay_arrival_nights"


class BulkRestrictionsUpdate(BulkRatePlanScope):
    min_advance_hours: int | None = Field(default=None, ge=0)
    max_advance_hours: int | None = Field(default=None, ge=0)
    min_stay_nights: int | None = Field(default=None, ge=1)
    min_stay_arrival_nights: int | None = Field(default=None, ge=1)
    clear: list[RestrictionField] = Field(default_factory=list)


class CopyRateAlignment(StrEnum):
    DAY_OF_WEEK = "day_of_week"
    DATE_ORDER = "date_order"
    CUSTOM_RANGE = "custom_range"


class CopyRateAdjustment(StrEnum):
    NONE = "none"
    INCREASE_PERCENT = "increase_percent"
    DECREASE_PERCENT = "decrease_percent"


class BulkCopyRates(BaseModel):
    sanatorium_id: uuid.UUID
    source_date_from: date
    source_date_to: date
    target_date_from: date
    target_date_to: date
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    rate_plan_ids: list[uuid.UUID] = Field(min_length=1)
    alignment: CopyRateAlignment = CopyRateAlignment.DAY_OF_WEEK
    overwrite_existing: bool = False
    adjustment: CopyRateAdjustment = CopyRateAdjustment.NONE
    adjustment_percent: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _validate(self):
        if self.source_date_from > self.source_date_to:
            raise ValueError("source_date_from must be on or before source_date_to")
        if self.target_date_from > self.target_date_to:
            raise ValueError("target_date_from must be on or before target_date_to")
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("weekdays must use Python weekday numbers: Monday=0")
        if (
            self.adjustment != CopyRateAdjustment.NONE
            and self.adjustment_percent is None
        ):
            raise ValueError("adjustment_percent is required for rate adjustments")
        return self


class BulkOperationResult(BaseModel):
    updated: int
