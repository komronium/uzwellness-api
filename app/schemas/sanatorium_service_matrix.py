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
