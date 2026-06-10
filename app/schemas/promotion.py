import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.utils import pick_locale
from app.models.promotion import (
    PromotionAudience,
    PromotionCancellationPolicyMode,
    PromotionCategory,
    PromotionStatus,
)
from app.schemas.common import Page, Translations, TranslationsCreate
from app.schemas.rate_plan import RatePlanAdminListRoom


class PromotionStats(BaseModel):
    reservations: int = 0
    revenue: Decimal = Decimal("0.00")
    room_nights: int = 0
    promotion_revenue: Decimal = Decimal("0.00")
    promotion_room_nights: int = 0


class PromotionCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: TranslationsCreate
    category: PromotionCategory = PromotionCategory.CUSTOM
    status: PromotionStatus = PromotionStatus.ACTIVE
    discount_percent: Decimal = Field(ge=0, le=100, decimal_places=2)
    booking_date_from: date | None = None
    booking_date_to: date | None = None
    stay_date_from: date | None = None
    stay_date_to: date | None = None
    booking_weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    stay_weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    booking_time_from: time | None = None
    booking_time_to: time | None = None
    rate_plan_ids: list[uuid.UUID] = Field(min_length=1)
    audience: PromotionAudience = PromotionAudience.ALL_GUESTS
    cancellation_policy_mode: PromotionCancellationPolicyMode = (
        PromotionCancellationPolicyMode.ORIGINAL
    )
    custom_cancellation_policy: dict = Field(default_factory=dict)
    pay_with_cost_per_sale_account: bool = False

    @model_validator(mode="after")
    def _validate(self):
        _validate_date_pair(self.booking_date_from, self.booking_date_to, "booking")
        _validate_date_pair(self.stay_date_from, self.stay_date_to, "stay")
        _validate_weekdays(self.booking_weekdays, "booking_weekdays")
        _validate_weekdays(self.stay_weekdays, "stay_weekdays")
        return self


class PromotionUpdate(BaseModel):
    name: Translations | None = None
    category: PromotionCategory | None = None
    status: PromotionStatus | None = None
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )
    booking_date_from: date | None = None
    booking_date_to: date | None = None
    stay_date_from: date | None = None
    stay_date_to: date | None = None
    booking_weekdays: list[int] | None = None
    stay_weekdays: list[int] | None = None
    booking_time_from: time | None = None
    booking_time_to: time | None = None
    rate_plan_ids: list[uuid.UUID] | None = None
    audience: PromotionAudience | None = None
    cancellation_policy_mode: PromotionCancellationPolicyMode | None = None
    custom_cancellation_policy: dict | None = None
    pay_with_cost_per_sale_account: bool | None = None

    @model_validator(mode="after")
    def _validate(self):
        _validate_date_pair(self.booking_date_from, self.booking_date_to, "booking")
        _validate_date_pair(self.stay_date_from, self.stay_date_to, "stay")
        if self.booking_weekdays is not None:
            _validate_weekdays(self.booking_weekdays, "booking_weekdays")
        if self.stay_weekdays is not None:
            _validate_weekdays(self.stay_weekdays, "stay_weekdays")
        return self


class PromotionRatePlanRead(BaseModel):
    id: uuid.UUID
    name: dict
    room: RatePlanAdminListRoom
    payment_timing: str
    confirmation: str

    @classmethod
    def from_obj(cls, obj) -> "PromotionRatePlanRead":
        return cls(
            id=obj.id,
            name=obj.name,
            room=RatePlanAdminListRoom(
                id=obj.room.id,
                name=obj.room.name,
                capacity=obj.room.capacity,
                is_active=obj.room.is_active,
            ),
            payment_timing=obj.payment_timing.value,
            confirmation=obj.confirmation.value,
        )


class PromotionListItem(BaseModel):
    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: str
    name_i18n: dict
    category: PromotionCategory
    status: PromotionStatus
    discount_percent: Decimal
    booking_date_from: date | None
    booking_date_to: date | None
    stay_date_from: date | None
    stay_date_to: date | None
    stats: PromotionStats
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_obj(
        cls, obj, *, locale: str, stats: PromotionStats
    ) -> "PromotionListItem":
        return cls(
            id=obj.id,
            sanatorium_id=obj.sanatorium_id,
            name=pick_locale(obj.name, locale),
            name_i18n=obj.name,
            category=obj.category,
            status=obj.status,
            discount_percent=obj.discount_percent,
            booking_date_from=obj.booking_date_from,
            booking_date_to=obj.booking_date_to,
            stay_date_from=obj.stay_date_from,
            stay_date_to=obj.stay_date_to,
            stats=stats,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class PromotionRead(PromotionListItem):
    booking_weekdays: list[int]
    stay_weekdays: list[int]
    booking_time_from: time | None
    booking_time_to: time | None
    rate_plans: list[PromotionRatePlanRead]
    audience: PromotionAudience
    cancellation_policy_mode: PromotionCancellationPolicyMode
    custom_cancellation_policy: dict
    pay_with_cost_per_sale_account: bool

    @classmethod
    def from_obj(cls, obj, *, locale: str, stats: PromotionStats) -> "PromotionRead":
        base = PromotionListItem.from_obj(obj, locale=locale, stats=stats)
        return cls(
            **base.model_dump(),
            booking_weekdays=obj.booking_weekdays,
            stay_weekdays=obj.stay_weekdays,
            booking_time_from=obj.booking_time_from,
            booking_time_to=obj.booking_time_to,
            rate_plans=[PromotionRatePlanRead.from_obj(rp) for rp in obj.rate_plans],
            audience=obj.audience,
            cancellation_policy_mode=obj.cancellation_policy_mode,
            custom_cancellation_policy=obj.custom_cancellation_policy,
            pay_with_cost_per_sale_account=obj.pay_with_cost_per_sale_account,
        )


class PromotionList(Page[PromotionListItem]):
    pass


def _validate_date_pair(start: date | None, end: date | None, label: str) -> None:
    if start is not None and end is not None and start > end:
        raise ValueError(f"{label}_date_from must be on or before {label}_date_to")


def _validate_weekdays(values: list[int], field: str) -> None:
    if any(day < 0 or day > 6 for day in values):
        raise ValueError(f"{field} must use Monday=0 through Sunday=6")
