from pydantic import BaseModel, Field

from app.core.utils import pick_locale
from app.models.amenity import AmenityCost
from app.schemas.common import Translations


class ServiceMatrixItem(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    title: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)
    is_available: bool = True
    cost: AmenityCost = AmenityCost.FREE
    hours: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    icon: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list)


class ServiceMatrixGroup(BaseModel):
    title: Translations = Field(default_factory=Translations)
    items: list[ServiceMatrixItem] = Field(default_factory=list)


class ServiceMatrix(BaseModel):
    food_drink: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    wellness: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    medical_department: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    front_desk: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    cleaning: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    business: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    parking: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    internet: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    children: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    accessibility: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    languages: list[str] = Field(default_factory=list)
    notes: Translations = Field(default_factory=Translations)


class ServiceMatrixItemRead(BaseModel):
    code: str
    title: str
    description: str
    is_available: bool
    cost: AmenityCost
    hours: str | None = None
    location: str | None = None
    icon: str | None = None
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_obj(cls, obj: dict | BaseModel, locale: str) -> "ServiceMatrixItemRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                title=pick_locale(obj.get("title", {}) or {}, locale),
                description=pick_locale(obj.get("description", {}) or {}, locale),
                is_available=obj.get("is_available", True),
                cost=obj.get("cost", AmenityCost.FREE),
                hours=obj.get("hours"),
                location=obj.get("location"),
                icon=obj.get("icon"),
                tags=obj.get("tags") or [],
            )
        return cls(
            code=getattr(obj, "code", ""),
            title=pick_locale(getattr(obj, "title", {}) or {}, locale),
            description=pick_locale(getattr(obj, "description", {}) or {}, locale),
            is_available=getattr(obj, "is_available", True),
            cost=getattr(obj, "cost", AmenityCost.FREE),
            hours=getattr(obj, "hours", None),
            location=getattr(obj, "location", None),
            icon=getattr(obj, "icon", None),
            tags=getattr(obj, "tags", []) or [],
        )


class ServiceMatrixGroupRead(BaseModel):
    title: str = ""
    items: list[ServiceMatrixItemRead] = Field(default_factory=list)

    @classmethod
    def from_obj(cls, obj: dict | None, locale: str) -> "ServiceMatrixGroupRead":
        if not obj:
            return cls(title="", items=[])
        return cls(
            title=pick_locale(obj.get("title", {}) or {}, locale),
            items=[
                ServiceMatrixItemRead.from_obj(item, locale)
                for item in (obj.get("items") or [])
            ],
        )


class ServiceMatrixRead(BaseModel):
    food_drink: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    wellness: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    medical_department: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    front_desk: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    cleaning: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    business: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    parking: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    internet: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    children: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    accessibility: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    languages: list[str] = Field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_obj(cls, obj: dict | None, locale: str) -> "ServiceMatrixRead":
        if not obj:
            return cls()
        return cls(
            food_drink=ServiceMatrixGroupRead.from_obj(obj.get("food_drink"), locale),
            wellness=ServiceMatrixGroupRead.from_obj(obj.get("wellness"), locale),
            medical_department=ServiceMatrixGroupRead.from_obj(
                obj.get("medical_department"), locale
            ),
            front_desk=ServiceMatrixGroupRead.from_obj(obj.get("front_desk"), locale),
            cleaning=ServiceMatrixGroupRead.from_obj(obj.get("cleaning"), locale),
            business=ServiceMatrixGroupRead.from_obj(obj.get("business"), locale),
            parking=ServiceMatrixGroupRead.from_obj(obj.get("parking"), locale),
            internet=ServiceMatrixGroupRead.from_obj(obj.get("internet"), locale),
            children=ServiceMatrixGroupRead.from_obj(obj.get("children"), locale),
            accessibility=ServiceMatrixGroupRead.from_obj(
                obj.get("accessibility"), locale
            ),
            languages=obj.get("languages") or [],
            notes=pick_locale(obj.get("notes", {}) or {}, locale),
        )


class StayInclusion(BaseModel):
    min_days: int = Field(..., ge=1)
    inclusions: list[str] = Field(default_factory=list)


class StayDurationColumn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    label: Translations = Field(default_factory=Translations)
    min_days: int = Field(..., ge=1)
    max_days: int | None = Field(default=None, ge=1)


class StayDurationColumnRead(BaseModel):
    code: str
    label: str
    min_days: int
    max_days: int | None = None

    @classmethod
    def from_obj(cls, obj: dict | BaseModel, locale: str) -> "StayDurationColumnRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                label=pick_locale(obj.get("label", {}) or {}, locale),
                min_days=obj.get("min_days", 1),
                max_days=obj.get("max_days"),
            )
        return cls(
            code=getattr(obj, "code", ""),
            label=pick_locale(getattr(obj, "label", {}) or {}, locale),
            min_days=getattr(obj, "min_days", 1),
            max_days=getattr(obj, "max_days", None),
        )


class StayProgramInclusion(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    title: Translations = Field(default_factory=Translations)
    category: str | None = Field(default=None, max_length=60)
    included_for: dict[str, bool] = Field(default_factory=dict)
    note: Translations = Field(default_factory=Translations)


class StayProgramInclusionRead(BaseModel):
    code: str
    title: str
    category: str | None = None
    included_for: dict[str, bool] = Field(default_factory=dict)
    note: str = ""

    @classmethod
    def from_obj(
        cls, obj: dict | BaseModel, locale: str
    ) -> "StayProgramInclusionRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                title=pick_locale(obj.get("title", {}) or {}, locale),
                category=obj.get("category"),
                included_for=obj.get("included_for") or {},
                note=pick_locale(obj.get("note", {}) or {}, locale),
            )
        return cls(
            code=getattr(obj, "code", ""),
            title=pick_locale(getattr(obj, "title", {}) or {}, locale),
            category=getattr(obj, "category", None),
            included_for=getattr(obj, "included_for", {}) or {},
            note=pick_locale(getattr(obj, "note", {}) or {}, locale),
        )


class MedicalProcedureItem(BaseModel):
    code: str = Field(..., min_length=1, max_length=60)
    image_url: str | None = Field(default=None, max_length=500)
    description: Translations = Field(default_factory=Translations)


class MedicalBase(BaseModel):
    description: Translations = Field(default_factory=Translations)
    procedures_per_week: int | None = Field(default=None, ge=0)
    min_age_for_treatment: int | None = Field(default=None, ge=0)
    checkups_included: int | None = Field(default=None, ge=0)
    natural_resources: list[str] = Field(default_factory=list)
    procedures: dict[str, list[MedicalProcedureItem]] = Field(default_factory=dict)
    stay_inclusions: list[StayInclusion] = Field(default_factory=list)
    stay_duration_columns: list[StayDurationColumn] = Field(default_factory=list)
    stay_program_inclusions: list[StayProgramInclusion] = Field(default_factory=list)


class MedicalProcedureItemRead(BaseModel):
    code: str
    image_url: str | None = None
    description: str

    @classmethod
    def from_obj(cls, obj: dict | BaseModel, locale: str) -> "MedicalProcedureItemRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                image_url=obj.get("image_url"),
                description=pick_locale(obj.get("description", {}) or {}, locale),
            )
        return cls(
            code=getattr(obj, "code", ""),
            image_url=getattr(obj, "image_url", None),
            description=pick_locale(getattr(obj, "description", {}), locale),
        )


class MedicalBaseRead(BaseModel):
    description: str
    procedures_per_week: int | None = None
    min_age_for_treatment: int | None = None
    checkups_included: int | None = None
    natural_resources: list[str] = Field(default_factory=list)
    procedures: dict[str, list[MedicalProcedureItemRead]] = Field(default_factory=dict)
    stay_inclusions: list[StayInclusion] = Field(default_factory=list)
    stay_duration_columns: list[StayDurationColumnRead] = Field(default_factory=list)
    stay_program_inclusions: list[StayProgramInclusionRead] = Field(
        default_factory=list
    )

    @classmethod
    def from_obj(cls, obj: dict | None, locale: str) -> "MedicalBaseRead":
        if not obj:
            return cls(
                description="",
                natural_resources=[],
                procedures={},
                stay_inclusions=[],
                stay_duration_columns=[],
                stay_program_inclusions=[],
            )

        proc_dict: dict[str, list[MedicalProcedureItemRead]] = {}
        for cat, items in (obj.get("procedures", {}) or {}).items():
            proc_dict[cat] = [
                MedicalProcedureItemRead.from_obj(item, locale) for item in items
            ]

        return cls(
            description=pick_locale(obj.get("description", {}) or {}, locale),
            procedures_per_week=obj.get("procedures_per_week"),
            min_age_for_treatment=obj.get("min_age_for_treatment"),
            checkups_included=obj.get("checkups_included"),
            natural_resources=obj.get("natural_resources") or [],
            procedures=proc_dict,
            stay_inclusions=[
                StayInclusion(**t) for t in (obj.get("stay_inclusions") or [])
            ],
            stay_duration_columns=[
                StayDurationColumnRead.from_obj(t, locale)
                for t in (obj.get("stay_duration_columns") or [])
            ],
            stay_program_inclusions=[
                StayProgramInclusionRead.from_obj(t, locale)
                for t in (obj.get("stay_program_inclusions") or [])
            ],
        )


class TreatmentProfileItem(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    title: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)


class TreatmentProfile(BaseModel):
    main_indications: list[TreatmentProfileItem] = Field(default_factory=list)
    additional_indications: list[TreatmentProfileItem] = Field(default_factory=list)
    contraindications: list[TreatmentProfileItem] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    doctor_specialties: list[str] = Field(default_factory=list)
    notes: Translations = Field(default_factory=Translations)


class TreatmentProfileItemRead(BaseModel):
    code: str
    title: str
    description: str

    @classmethod
    def from_obj(cls, obj: dict | BaseModel, locale: str) -> "TreatmentProfileItemRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                title=pick_locale(obj.get("title", {}) or {}, locale),
                description=pick_locale(obj.get("description", {}) or {}, locale),
            )
        return cls(
            code=getattr(obj, "code", ""),
            title=pick_locale(getattr(obj, "title", {}) or {}, locale),
            description=pick_locale(getattr(obj, "description", {}) or {}, locale),
        )


class TreatmentProfileRead(BaseModel):
    main_indications: list[TreatmentProfileItemRead] = Field(default_factory=list)
    additional_indications: list[TreatmentProfileItemRead] = Field(default_factory=list)
    contraindications: list[TreatmentProfileItemRead] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    doctor_specialties: list[str] = Field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_obj(cls, obj: dict | None, locale: str) -> "TreatmentProfileRead":
        if not obj:
            return cls()
        return cls(
            main_indications=[
                TreatmentProfileItemRead.from_obj(item, locale)
                for item in (obj.get("main_indications") or [])
            ],
            additional_indications=[
                TreatmentProfileItemRead.from_obj(item, locale)
                for item in (obj.get("additional_indications") or [])
            ],
            contraindications=[
                TreatmentProfileItemRead.from_obj(item, locale)
                for item in (obj.get("contraindications") or [])
            ],
            diagnostics=obj.get("diagnostics") or [],
            doctor_specialties=obj.get("doctor_specialties") or [],
            notes=pick_locale(obj.get("notes", {}) or {}, locale),
        )
