import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.models.program import (
    TreatmentGuestApplicability,
    TreatmentProgramType,
    TreatmentStayPackageKind,
)
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations, TranslationsCreate


class TreatmentProgramCreate(BaseModel):
    sanatorium_id: uuid.UUID
    focus_id: uuid.UUID | None = None
    name: TranslationsCreate
    description: TranslationsCreate
    program_type: TreatmentProgramType = TreatmentProgramType.SESSION
    stay_package_kind: TreatmentStayPackageKind = TreatmentStayPackageKind.TREATMENT
    guest_applicability: TreatmentGuestApplicability = TreatmentGuestApplicability.ALL
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    duration_minutes: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    instructor_name: str | None = Field(default=None, max_length=255)
    instructor_bio: Translations = Field(default_factory=Translations)
    group_size_min: int | None = Field(default=None, ge=1)
    group_size_max: int | None = Field(default=None, ge=1)
    what_to_bring: Translations = Field(default_factory=Translations)
    medical_exam_count: int = Field(default=0, ge=0)
    medical_procedure_count: int = Field(default=0, ge=0)
    drink_cure_included: bool = False
    sauna_entries: int | None = Field(default=None, ge=0)
    pool_access_included: bool = False
    included_services: list[str] = Field(default_factory=list)
    is_default_stay_package: bool = False
    display_order: int = Field(default=0, ge=0)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)


class TreatmentProgramUpdate(BaseModel):
    focus_id: uuid.UUID | None = None
    name: Translations | None = None
    description: Translations | None = None
    program_type: TreatmentProgramType | None = None
    stay_package_kind: TreatmentStayPackageKind | None = None
    guest_applicability: TreatmentGuestApplicability | None = None
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    duration_minutes: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    instructor_name: str | None = Field(default=None, max_length=255)
    instructor_bio: Translations | None = None
    group_size_min: int | None = Field(default=None, ge=1)
    group_size_max: int | None = Field(default=None, ge=1)
    what_to_bring: Translations | None = None
    medical_exam_count: int | None = Field(default=None, ge=0)
    medical_procedure_count: int | None = Field(default=None, ge=0)
    drink_cure_included: bool | None = None
    sauna_entries: int | None = Field(default=None, ge=0)
    pool_access_included: bool | None = None
    included_services: list[str] | None = None
    is_default_stay_package: bool | None = None
    display_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    amenity_ids: list[uuid.UUID] | None = None


class TreatmentProgramRead(BaseModel):
    id: uuid.UUID
    sanatorium_id: uuid.UUID
    focus_id: uuid.UUID | None
    name: str
    description: str
    program_type: TreatmentProgramType
    stay_package_kind: TreatmentStayPackageKind
    guest_applicability: TreatmentGuestApplicability
    min_nights: int | None
    max_nights: int | None
    duration_minutes: int | None
    price: Decimal | None
    currency: str | None
    instructor_name: str | None
    instructor_bio: str
    group_size_min: int | None
    group_size_max: int | None
    what_to_bring: str
    medical_exam_count: int
    medical_procedure_count: int
    drink_cure_included: bool
    sauna_entries: int | None
    pool_access_included: bool
    included_services: list[str]
    is_default_stay_package: bool
    display_order: int
    is_active: bool
    amenities: list[AmenityRead]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_obj(cls, obj, locale: str) -> "TreatmentProgramRead":
        return cls(
            id=obj.id,
            sanatorium_id=obj.sanatorium_id,
            focus_id=obj.focus_id,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            program_type=obj.program_type,
            stay_package_kind=obj.stay_package_kind,
            guest_applicability=obj.guest_applicability,
            min_nights=obj.min_nights,
            max_nights=obj.max_nights,
            duration_minutes=obj.duration_minutes,
            price=obj.price,
            currency=obj.currency,
            instructor_name=obj.instructor_name,
            instructor_bio=pick_locale(obj.instructor_bio, locale),
            group_size_min=obj.group_size_min,
            group_size_max=obj.group_size_max,
            what_to_bring=pick_locale(obj.what_to_bring, locale),
            medical_exam_count=obj.medical_exam_count,
            medical_procedure_count=obj.medical_procedure_count,
            drink_cure_included=obj.drink_cure_included,
            sauna_entries=obj.sauna_entries,
            pool_access_included=obj.pool_access_included,
            included_services=obj.included_services,
            is_default_stay_package=obj.is_default_stay_package,
            display_order=obj.display_order,
            is_active=obj.is_active,
            amenities=[AmenityRead.from_obj(a, locale) for a in obj.amenities],
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class TreatmentProgramAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    focus_id: uuid.UUID | None
    name: dict
    description: dict
    program_type: TreatmentProgramType
    stay_package_kind: TreatmentStayPackageKind
    guest_applicability: TreatmentGuestApplicability
    min_nights: int | None
    max_nights: int | None
    duration_minutes: int | None
    price: Decimal | None
    currency: str | None
    instructor_name: str | None
    instructor_bio: dict
    group_size_min: int | None
    group_size_max: int | None
    what_to_bring: dict
    medical_exam_count: int
    medical_procedure_count: int
    drink_cure_included: bool
    sauna_entries: int | None
    pool_access_included: bool
    included_services: list[str]
    is_default_stay_package: bool
    display_order: int
    is_active: bool
    amenities: list[AmenityAdminRead]
    created_at: datetime
    updated_at: datetime


class TreatmentProgramList(BaseModel):
    items: list[TreatmentProgramRead]
    total: int
    limit: int
    offset: int


class TreatmentProgramAdminList(BaseModel):
    items: list[TreatmentProgramAdminRead]
    total: int
    limit: int
    offset: int
