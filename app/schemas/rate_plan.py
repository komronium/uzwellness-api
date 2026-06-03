import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations, TranslationsCreate


class RatePlanCreate(BaseModel):
    room_id: uuid.UUID
    name: TranslationsCreate
    board: BoardType = BoardType.ROOM_ONLY
    board_optional: bool = False
    board_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    board_guests: int | None = Field(default=None, ge=1)
    refundable: bool = True
    free_cancellation_days: int | None = Field(default=None, ge=0)
    cancellation_penalty_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )
    cancellation_penalty_amount: Decimal | None = Field(
        default=None, ge=0, decimal_places=2
    )
    payment_timing: PaymentTiming = PaymentTiming.PREPAY
    confirmation: ConfirmationType = ConfirmationType.INSTANT
    price_adjustment_percent: Decimal | None = Field(
        default=None, ge=-100, le=100, decimal_places=2
    )
    promo_label: str | None = Field(default=None, max_length=60)
    promo_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    promo_starts_at: datetime | None = None
    promo_ends_at: datetime | None = None
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)


class RatePlanUpdate(BaseModel):
    name: Translations | None = None
    board: BoardType | None = None
    board_optional: bool | None = None
    board_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    board_guests: int | None = Field(default=None, ge=1)
    refundable: bool | None = None
    free_cancellation_days: int | None = Field(default=None, ge=0)
    cancellation_penalty_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )
    cancellation_penalty_amount: Decimal | None = Field(
        default=None, ge=0, decimal_places=2
    )
    payment_timing: PaymentTiming | None = None
    confirmation: ConfirmationType | None = None
    price_adjustment_percent: Decimal | None = Field(
        default=None, ge=-100, le=100, decimal_places=2
    )
    promo_label: str | None = Field(default=None, max_length=60)
    promo_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    promo_starts_at: datetime | None = None
    promo_ends_at: datetime | None = None
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    amenity_ids: list[uuid.UUID] | None = None


class _RatePlanCommon(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    board: BoardType
    board_optional: bool
    board_price: Decimal | None
    board_guests: int | None
    refundable: bool
    free_cancellation_days: int | None
    cancellation_penalty_percent: Decimal | None
    cancellation_penalty_amount: Decimal | None
    payment_timing: PaymentTiming
    confirmation: ConfirmationType
    price_adjustment_percent: Decimal | None
    promo_label: str | None
    promo_percent: Decimal | None
    promo_starts_at: datetime | None
    promo_ends_at: datetime | None
    min_nights: int | None
    max_nights: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RatePlanRead(_RatePlanCommon):
    name: str
    amenities: list[AmenityRead] = Field(default_factory=list)

    @classmethod
    def from_obj(cls, obj, locale: str) -> "RatePlanRead":
        return cls(
            id=obj.id,
            room_id=obj.room_id,
            name=pick_locale(obj.name, locale),
            board=obj.board,
            board_optional=obj.board_optional,
            board_price=obj.board_price,
            board_guests=obj.board_guests,
            refundable=obj.refundable,
            free_cancellation_days=obj.free_cancellation_days,
            cancellation_penalty_percent=obj.cancellation_penalty_percent,
            cancellation_penalty_amount=obj.cancellation_penalty_amount,
            payment_timing=obj.payment_timing,
            confirmation=obj.confirmation,
            price_adjustment_percent=obj.price_adjustment_percent,
            promo_label=obj.promo_label,
            promo_percent=obj.promo_percent,
            promo_starts_at=obj.promo_starts_at,
            promo_ends_at=obj.promo_ends_at,
            min_nights=obj.min_nights,
            max_nights=obj.max_nights,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            amenities=[AmenityRead.from_obj(a, locale) for a in obj.amenities],
        )


class RatePlanAdminRead(_RatePlanCommon):
    model_config = ConfigDict(from_attributes=True)

    name: dict
    amenities: list[AmenityAdminRead] = Field(default_factory=list)


class RatePlanAdminListRoom(BaseModel):
    id: uuid.UUID
    name: dict
    capacity: int
    is_active: bool


class RatePlanAdminDirectoryItem(_RatePlanCommon):
    name: dict
    room: RatePlanAdminListRoom
    amenities: list[AmenityAdminRead] = Field(default_factory=list)
    cancellation_policy_summary: str
    meals_summary: str
    restrictions_summary: str
    rate_status_summary: str
    status: str

    @classmethod
    def from_obj(cls, obj) -> "RatePlanAdminDirectoryItem":
        return cls(
            id=obj.id,
            room_id=obj.room_id,
            room=RatePlanAdminListRoom(
                id=obj.room.id,
                name=obj.room.name,
                capacity=obj.room.capacity,
                is_active=obj.room.is_active,
            ),
            name=obj.name,
            board=obj.board,
            board_optional=obj.board_optional,
            board_price=obj.board_price,
            board_guests=obj.board_guests,
            refundable=obj.refundable,
            free_cancellation_days=obj.free_cancellation_days,
            cancellation_penalty_percent=obj.cancellation_penalty_percent,
            cancellation_penalty_amount=obj.cancellation_penalty_amount,
            payment_timing=obj.payment_timing,
            confirmation=obj.confirmation,
            price_adjustment_percent=obj.price_adjustment_percent,
            promo_label=obj.promo_label,
            promo_percent=obj.promo_percent,
            promo_starts_at=obj.promo_starts_at,
            promo_ends_at=obj.promo_ends_at,
            min_nights=obj.min_nights,
            max_nights=obj.max_nights,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            amenities=[AmenityAdminRead.model_validate(a) for a in obj.amenities],
            cancellation_policy_summary=_cancellation_policy_summary(obj),
            meals_summary=_meals_summary(obj),
            restrictions_summary=_restrictions_summary(obj),
            rate_status_summary="Set in calendar",
            status="active" if obj.is_active else "inactive",
        )


class RatePlanList(BaseModel):
    items: list[RatePlanRead]
    total: int
    limit: int
    offset: int


class RatePlanAdminList(BaseModel):
    items: list[RatePlanAdminRead]
    total: int
    limit: int
    offset: int


class RatePlanAdminDirectoryList(BaseModel):
    items: list[RatePlanAdminDirectoryItem]
    total: int
    limit: int
    offset: int


def _cancellation_policy_summary(obj) -> str:
    if not obj.refundable:
        return "Non-refundable"
    if obj.free_cancellation_days is not None:
        return f"Free cancellation until {obj.free_cancellation_days} day(s) before arrival"
    if obj.cancellation_penalty_percent is not None:
        return f"Penalty {obj.cancellation_penalty_percent}%"
    if obj.cancellation_penalty_amount is not None:
        return f"Penalty {obj.cancellation_penalty_amount}"
    return "Flexible"


def _meals_summary(obj) -> str:
    if obj.board == BoardType.ROOM_ONLY:
        return "No meals"
    guests = obj.board_guests or 1
    suffix = "paid add-on" if obj.board_optional else "included"
    return f"{guests} x {obj.board.value.replace('_', ' ')} per guest ({suffix})"


def _restrictions_summary(obj) -> str:
    restrictions = []
    if obj.min_nights is not None:
        restrictions.append(f"min {obj.min_nights} night(s)")
    if obj.max_nights is not None:
        restrictions.append(f"max {obj.max_nights} night(s)")
    return ", ".join(restrictions) if restrictions else "None"
