import uuid
from datetime import time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Translations

ChildRateMode = Literal["standard", "flexible", "children_as_adults"]
ChildPricingMethod = Literal["free", "same_as_adults", "fixed"]
TaxFeeCalculationMethod = Literal[
    "per_room_per_night_percent",
    "per_room_per_night_fixed",
    "per_person_per_night_percent",
    "per_person_per_night_fixed",
    "per_booking_percent",
    "per_booking_fixed",
]
TaxFeeLevel = Literal["property", "room"]
TaxFeeType = Literal[
    "vat", "tourism_tax", "city_tax", "resort_fee", "service_fee", "custom"
]
TaxPricingMode = Literal["tax_inclusive", "tax_exclusive"]


class PolicySection(BaseModel):
    notes: Translations = Field(default_factory=Translations)


class PolicySectionUpdate(BaseModel):
    notes: Translations | None = None


class CheckInPolicy(PolicySection):
    instructions: Translations = Field(default_factory=Translations)
    required_documents: list[str] = Field(default_factory=list)
    latest_check_in_time: time | None = None
    earliest_check_out_time: time | None = None
    front_desk_available: bool | None = None
    front_desk_24h: bool | None = None
    front_desk_opens_at: time | None = None
    front_desk_closes_at: time | None = None
    staff_greet_on_arrival: bool | None = None
    self_check_in_available: bool | None = None
    check_in_at_another_location: bool | None = None
    must_contact_before_check_in: bool | None = None
    sends_check_in_guide: bool | None = None


class CheckInPolicyUpdate(PolicySectionUpdate):
    instructions: Translations | None = None
    required_documents: list[str] | None = None
    latest_check_in_time: time | None = None
    earliest_check_out_time: time | None = None
    front_desk_available: bool | None = None
    front_desk_24h: bool | None = None
    front_desk_opens_at: time | None = None
    front_desk_closes_at: time | None = None
    staff_greet_on_arrival: bool | None = None
    self_check_in_available: bool | None = None
    check_in_at_another_location: bool | None = None
    must_contact_before_check_in: bool | None = None
    sends_check_in_guide: bool | None = None


class ImportantNotice(BaseModel):
    title: Translations = Field(default_factory=Translations)
    body: Translations = Field(default_factory=Translations)
    category: str | None = Field(default=None, max_length=80)
    valid_from: str | None = Field(default=None, max_length=40)
    valid_to: str | None = Field(default=None, max_length=40)


class ImportantNoticeUpdate(BaseModel):
    title: Translations | None = None
    body: Translations | None = None
    category: str | None = Field(default=None, max_length=80)
    valid_from: str | None = Field(default=None, max_length=40)
    valid_to: str | None = Field(default=None, max_length=40)


class ImportantNoticesPolicy(PolicySection):
    items: list[ImportantNotice] = Field(default_factory=list)


class ImportantNoticesPolicyUpdate(PolicySectionUpdate):
    items: list[ImportantNoticeUpdate] | None = None


class ChildExistingBedPriceBand(BaseModel):
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    pricing_method: ChildPricingMethod = "same_as_adults"
    price_per_night: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: Translations = Field(default_factory=Translations)


class ChildExistingBedPriceBandUpdate(BaseModel):
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    pricing_method: ChildPricingMethod | None = None
    price_per_night: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: Translations | None = None


class ChildrenPolicy(PolicySection):
    allowed: bool | None = None
    min_age: int | None = Field(default=None, ge=0, le=120)
    treatment_min_age: int | None = Field(default=None, ge=0, le=120)
    child_rate_mode: ChildRateMode | None = None
    child_rates_prepaid: bool | None = None
    existing_bed_price_bands: list[ChildExistingBedPriceBand] = Field(
        default_factory=list
    )


class ChildrenPolicyUpdate(PolicySectionUpdate):
    allowed: bool | None = None
    min_age: int | None = Field(default=None, ge=0, le=120)
    treatment_min_age: int | None = Field(default=None, ge=0, le=120)
    child_rate_mode: ChildRateMode | None = None
    child_rates_prepaid: bool | None = None
    existing_bed_price_bands: list[ChildExistingBedPriceBandUpdate] | None = None


class AgePriceBand(BaseModel):
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    price_per_night: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    includes: list[str] = Field(default_factory=list)
    notes: Translations = Field(default_factory=Translations)


class ExtraBedPolicy(PolicySection):
    available: bool | None = None
    crib_available: bool | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    age_price_bands: list[AgePriceBand] = Field(default_factory=list)


class ExtraBedPolicyUpdate(PolicySectionUpdate):
    available: bool | None = None
    crib_available: bool | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    age_price_bands: list[AgePriceBand] | None = None


class BreakfastPolicy(PolicySection):
    included: bool | None = None
    available: bool | None = None
    price: Decimal | None = Field(default=None, ge=0)
    adult_price: Decimal | None = Field(default=None, ge=0)
    child_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    style: str | None = Field(default=None, max_length=60)
    serving_style: str | None = Field(default=None, max_length=60)
    cuisine: str | None = Field(default=None, max_length=80)
    hours: str | None = Field(default=None, max_length=120)
    hours_by_weekday: dict[str, str] = Field(default_factory=dict)


class BreakfastPolicyUpdate(PolicySectionUpdate):
    included: bool | None = None
    available: bool | None = None
    price: Decimal | None = Field(default=None, ge=0)
    adult_price: Decimal | None = Field(default=None, ge=0)
    child_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    style: str | None = Field(default=None, max_length=60)
    serving_style: str | None = Field(default=None, max_length=60)
    cuisine: str | None = Field(default=None, max_length=80)
    hours: str | None = Field(default=None, max_length=120)
    hours_by_weekday: dict[str, str] | None = None


class PetPolicy(PolicySection):
    allowed: bool | None = None
    service_animals_allowed: bool | None = None
    fee: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fee_frequency: str | None = Field(default=None, max_length=40)
    advance_notice_required: bool | None = None


class PetPolicyUpdate(PolicySectionUpdate):
    allowed: bool | None = None
    service_animals_allowed: bool | None = None
    fee: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fee_frequency: str | None = Field(default=None, max_length=40)
    advance_notice_required: bool | None = None


class CancellationPolicyDetails(PolicySection):
    free_cancellation_until_days_before: int | None = Field(default=None, ge=0)
    penalty_percent: Decimal | None = Field(default=None, ge=0, le=100)


class CancellationPolicyDetailsUpdate(PolicySectionUpdate):
    free_cancellation_until_days_before: int | None = Field(default=None, ge=0)
    penalty_percent: Decimal | None = Field(default=None, ge=0, le=100)


class DepositPolicy(PolicySection):
    required: bool | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    percent: Decimal | None = Field(default=None, ge=0, le=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    type: str | None = Field(default=None, max_length=40)


class DepositPolicyUpdate(PolicySectionUpdate):
    required: bool | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    percent: Decimal | None = Field(default=None, ge=0, le=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    type: str | None = Field(default=None, max_length=40)


class PaymentPolicy(PolicySection):
    methods: list[str] = Field(default_factory=list)
    deposit_required: bool | None = None
    deposit_percent: Decimal | None = Field(default=None, ge=0, le=100)
    guarantee_methods: list[str] = Field(default_factory=list)
    accepted_cards: list[str] = Field(default_factory=list)


class PaymentPolicyUpdate(PolicySectionUpdate):
    methods: list[str] | None = None
    deposit_required: bool | None = None
    deposit_percent: Decimal | None = Field(default=None, ge=0, le=100)
    guarantee_methods: list[str] | None = None
    accepted_cards: list[str] | None = None


class TaxFeeRule(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    type: TaxFeeType
    level: TaxFeeLevel = "property"
    room_ids: list[uuid.UUID] = Field(default_factory=list)
    title: Translations = Field(default_factory=Translations)
    calculation_method: TaxFeeCalculationMethod
    amount: Decimal = Field(ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    active: bool = True
    postpay: bool = False
    included_in_price: bool = True
    include_in_promotion_calculations: bool = True
    separate_children_rule: bool = False
    calculation_order: int = Field(default=0, ge=0)
    valid_from: str | None = Field(default=None, max_length=40)
    valid_to: str | None = Field(default=None, max_length=40)
    notes: Translations = Field(default_factory=Translations)


class TaxFeeRuleUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    type: TaxFeeType | None = None
    level: TaxFeeLevel | None = None
    room_ids: list[uuid.UUID] | None = None
    title: Translations | None = None
    calculation_method: TaxFeeCalculationMethod | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    active: bool | None = None
    postpay: bool | None = None
    included_in_price: bool | None = None
    include_in_promotion_calculations: bool | None = None
    separate_children_rule: bool | None = None
    calculation_order: int | None = Field(default=None, ge=0)
    valid_from: str | None = Field(default=None, max_length=40)
    valid_to: str | None = Field(default=None, max_length=40)
    notes: Translations | None = None


class FeePolicy(PolicySection):
    pricing_mode: TaxPricingMode | None = None
    tax_rules: list[TaxFeeRule] = Field(default_factory=list)
    mandatory_fees: list[str] = Field(default_factory=list)
    optional_fees: list[str] = Field(default_factory=list)


class FeePolicyUpdate(PolicySectionUpdate):
    pricing_mode: TaxPricingMode | None = None
    tax_rules: list[TaxFeeRuleUpdate] | None = None
    mandatory_fees: list[str] | None = None
    optional_fees: list[str] | None = None


class ReservationRestrictionPolicy(PolicySection):
    cutoff_hours_before_check_in: int | None = Field(default=None, ge=0)
    min_advance_hours: int | None = Field(default=None, ge=0)
    max_advance_days: int | None = Field(default=None, ge=0)


class ReservationRestrictionPolicyUpdate(PolicySectionUpdate):
    cutoff_hours_before_check_in: int | None = Field(default=None, ge=0)
    min_advance_hours: int | None = Field(default=None, ge=0)
    max_advance_days: int | None = Field(default=None, ge=0)


class SanatoriumPolicies(BaseModel):
    check_in: CheckInPolicy = Field(default_factory=CheckInPolicy)
    important_notices: ImportantNoticesPolicy = Field(
        default_factory=ImportantNoticesPolicy
    )
    children: ChildrenPolicy = Field(default_factory=ChildrenPolicy)
    extra_bed: ExtraBedPolicy = Field(default_factory=ExtraBedPolicy)
    breakfast: BreakfastPolicy = Field(default_factory=BreakfastPolicy)
    pets: PetPolicy = Field(default_factory=PetPolicy)
    cancellation: CancellationPolicyDetails = Field(
        default_factory=CancellationPolicyDetails
    )
    deposit: DepositPolicy = Field(default_factory=DepositPolicy)
    payment: PaymentPolicy = Field(default_factory=PaymentPolicy)
    fees: FeePolicy = Field(default_factory=FeePolicy)
    reservation_restrictions: ReservationRestrictionPolicy = Field(
        default_factory=ReservationRestrictionPolicy
    )


class SanatoriumPoliciesUpdate(BaseModel):
    check_in: CheckInPolicyUpdate | None = None
    important_notices: ImportantNoticesPolicyUpdate | None = None
    children: ChildrenPolicyUpdate | None = None
    extra_bed: ExtraBedPolicyUpdate | None = None
    breakfast: BreakfastPolicyUpdate | None = None
    pets: PetPolicyUpdate | None = None
    cancellation: CancellationPolicyDetailsUpdate | None = None
    deposit: DepositPolicyUpdate | None = None
    payment: PaymentPolicyUpdate | None = None
    fees: FeePolicyUpdate | None = None
    reservation_restrictions: ReservationRestrictionPolicyUpdate | None = None
