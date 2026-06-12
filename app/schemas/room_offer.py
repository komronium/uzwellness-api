import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.booking import BookingType
from app.models.rate_plan import BoardType
from app.models.rate_plan import ConfirmationType, PaymentTiming


class RoomOfferSort(StrEnum):
    CHEAPEST = "cheapest"
    HIGHEST_PRICE = "highest_price"


class RoomOfferGuestType(StrEnum):
    ADULT = "adult"
    CHILD = "child"


class RoomOfferPackageKind(StrEnum):
    TREATMENT = "treatment"
    SPECIAL = "special"


class RoomOfferChild(BaseModel):
    age: int = Field(ge=0, le=17)


class RoomOfferRequestedRoom(BaseModel):
    adults: int = Field(ge=1)
    children: list[RoomOfferChild] = Field(default_factory=list)
    board: BoardType = BoardType.FULL_BOARD

    @property
    def guests_count(self) -> int:
        return self.adults + len(self.children)


class RoomOfferFilters(BaseModel):
    room_type_ids: list[uuid.UUID] = Field(default_factory=list)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_price_range(self):
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_max < self.price_min
        ):
            raise ValueError("price_max must be greater than or equal to price_min")
        return self


class RoomOfferTreatmentSelection(BaseModel):
    room_index: int = Field(ge=0)
    guest_index: int = Field(ge=0)
    program_id: uuid.UUID


class RoomOfferGuestOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_index: int = Field(ge=0)
    guest_index: int = Field(ge=0)
    board: BoardType | None = None
    treatment_included: bool = True

    @property
    def package_kind(self) -> RoomOfferPackageKind:
        return (
            RoomOfferPackageKind.TREATMENT
            if self.treatment_included
            else RoomOfferPackageKind.SPECIAL
        )


class RoomOfferSearchRequest(BaseModel):
    check_in: date
    check_out: date
    rooms: list[RoomOfferRequestedRoom] = Field(min_length=1, max_length=8)
    guest_options: list[RoomOfferGuestOption] = Field(default_factory=list)
    treatment_selections: list[RoomOfferTreatmentSelection] = Field(
        default_factory=list
    )
    filters: RoomOfferFilters = Field(default_factory=RoomOfferFilters)
    sort: RoomOfferSort = RoomOfferSort.CHEAPEST

    @model_validator(mode="after")
    def _validate_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        for option in self.guest_options:
            self._validate_guest_reference(option.room_index, option.guest_index)
        for selection in self.treatment_selections:
            self._validate_guest_reference(selection.room_index, selection.guest_index)
        return self

    def _validate_guest_reference(self, room_index: int, guest_index: int) -> None:
        if room_index >= len(self.rooms):
            raise ValueError("room_index does not exist")
        if guest_index >= self.rooms[room_index].guests_count:
            raise ValueError("guest_index does not exist in the selected room")


class RoomOfferGuest(BaseModel):
    guest_index: int
    type: RoomOfferGuestType
    age: int | None = None


class RoomOfferTreatmentOption(BaseModel):
    id: uuid.UUID
    package_kind: RoomOfferPackageKind
    name: str
    description: str | None
    duration_minutes: int | None
    medical_exam_count: int
    medical_procedure_count: int
    drink_cure_included: bool
    sauna_entries: int | None
    pool_access_included: bool
    included_services: list[str]
    price: Decimal | None
    currency: str | None
    price_delta: Decimal
    display_price: Decimal | None = None
    display_price_delta: Decimal | None = None
    display_currency: str | None = None


class RoomOfferTreatmentGroup(BaseModel):
    room_index: int
    guest: RoomOfferGuest
    board: BoardType
    package_kind: RoomOfferPackageKind
    selected_program_id: uuid.UUID | None
    options: list[RoomOfferTreatmentOption]


class RoomOfferPhoto(BaseModel):
    id: uuid.UUID
    url: str
    is_primary: bool
    order: int
    caption: str | None = None


class RoomOfferInclusion(BaseModel):
    type: str
    title: str
    description: str | None = None


class RoomOfferGuestInclusions(BaseModel):
    room_index: int
    guest: RoomOfferGuest
    items: list[RoomOfferInclusion]


class RoomOfferPrice(BaseModel):
    total: Decimal
    original_total: Decimal | None = None
    currency: str
    display_total: Decimal | None = None
    display_currency: str | None = None
    rooms_count: int
    adults: int
    children: int
    guests: int
    min_stay_nights: int | None = None
    payment_timing: PaymentTiming | None = None
    confirmation: ConfirmationType | None = None
    refundable: bool | None = None
    free_cancellation_days: int | None = None
    cancellation_penalty_percent: Decimal | None = None
    cancellation_penalty_amount: Decimal | None = None


class RoomOfferCard(BaseModel):
    offer_id: str
    booking_type: BookingType = BookingType.ROOM
    room_id: uuid.UUID
    rate_plan_id: uuid.UUID | None = None
    room_name: str
    rate_plan_name: str | None = None
    capacity: int
    max_adults: int | None
    max_children: int | None
    available_rooms: int
    photo_count: int
    photos: list[RoomOfferPhoto]
    price: RoomOfferPrice
    inclusions: list[RoomOfferGuestInclusions]


class RoomOfferAlternativeDate(BaseModel):
    check_in: date
    check_out: date
    nights: int
    min_total_price: Decimal
    currency: str
    display_min_total_price: Decimal | None = None
    display_currency: str | None = None


class RoomOfferSearchResponse(BaseModel):
    sanatorium_id: uuid.UUID
    check_in: date
    check_out: date
    nights: int
    rooms_count: int
    adults: int
    children: int
    guests: int
    available_count: int
    treatment_selection: list[RoomOfferTreatmentGroup]
    offers: list[RoomOfferCard]
    alternatives: list[RoomOfferAlternativeDate] = Field(default_factory=list)
