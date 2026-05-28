from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Translations


class PolicySection(BaseModel):
    notes: Translations = Field(default_factory=Translations)


class CheckInPolicy(PolicySection):
    instructions: Translations = Field(default_factory=Translations)
    required_documents: list[str] = Field(default_factory=list)


class ChildrenPolicy(PolicySection):
    allowed: bool | None = None
    min_age: int | None = Field(default=None, ge=0, le=120)
    treatment_min_age: int | None = Field(default=None, ge=0, le=120)


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


class BreakfastPolicy(PolicySection):
    included: bool | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    style: str | None = Field(default=None, max_length=60)
    hours: str | None = Field(default=None, max_length=120)


class PetPolicy(PolicySection):
    allowed: bool | None = None
    service_animals_allowed: bool | None = None
    fee: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class CancellationPolicyDetails(PolicySection):
    free_cancellation_until_days_before: int | None = Field(default=None, ge=0)
    penalty_percent: Decimal | None = Field(default=None, ge=0, le=100)


class PaymentPolicy(PolicySection):
    methods: list[str] = Field(default_factory=list)
    deposit_required: bool | None = None
    deposit_percent: Decimal | None = Field(default=None, ge=0, le=100)


class FeePolicy(PolicySection):
    mandatory_fees: list[str] = Field(default_factory=list)
    optional_fees: list[str] = Field(default_factory=list)


class SanatoriumPolicies(BaseModel):
    check_in: CheckInPolicy = Field(default_factory=CheckInPolicy)
    children: ChildrenPolicy = Field(default_factory=ChildrenPolicy)
    extra_bed: ExtraBedPolicy = Field(default_factory=ExtraBedPolicy)
    breakfast: BreakfastPolicy = Field(default_factory=BreakfastPolicy)
    pets: PetPolicy = Field(default_factory=PetPolicy)
    cancellation: CancellationPolicyDetails = Field(
        default_factory=CancellationPolicyDetails
    )
    payment: PaymentPolicy = Field(default_factory=PaymentPolicy)
    fees: FeePolicy = Field(default_factory=FeePolicy)
