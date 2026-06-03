from typing import Literal

from pydantic import BaseModel, Field

from app.core.utils import pick_locale
from app.models.amenity import AmenityCost
from app.schemas.common import Translations


class ServiceMatrixItem(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    title: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)
    status: Literal["yes", "no", "not_specified"] = "yes"
    is_available: bool = True
    cost: AmenityCost = AmenityCost.FREE
    hours: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    icon: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class ServiceMatrixGroup(BaseModel):
    title: Translations = Field(default_factory=Translations)
    items: list[ServiceMatrixItem] = Field(default_factory=list)


class ServiceMatrix(BaseModel):
    popular_facilities: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    food_drink: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    dining: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    wellness: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    medical_department: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    transport: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    front_desk: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    cleaning: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    cleaning_services: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    safety_security: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    recreational_activities: ServiceMatrixGroup = Field(
        default_factory=ServiceMatrixGroup
    )
    public_areas: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    business: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    amenities_for_kids: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    health_wellness: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
    sport_fitness: ServiceMatrixGroup = Field(default_factory=ServiceMatrixGroup)
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
    status: Literal["yes", "no", "not_specified"]
    is_available: bool
    cost: AmenityCost
    hours: str | None = None
    location: str | None = None
    icon: str | None = None
    tags: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)

    @classmethod
    def from_obj(cls, obj: dict | BaseModel, locale: str) -> "ServiceMatrixItemRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                title=pick_locale(obj.get("title", {}) or {}, locale),
                description=pick_locale(obj.get("description", {}) or {}, locale),
                status=obj.get("status", "yes"),
                is_available=obj.get("is_available", True),
                cost=obj.get("cost", AmenityCost.FREE),
                hours=obj.get("hours"),
                location=obj.get("location"),
                icon=obj.get("icon"),
                tags=obj.get("tags") or [],
                details=obj.get("details") or {},
            )
        return cls(
            code=getattr(obj, "code", ""),
            title=pick_locale(getattr(obj, "title", {}) or {}, locale),
            description=pick_locale(getattr(obj, "description", {}) or {}, locale),
            status=getattr(obj, "status", "yes"),
            is_available=getattr(obj, "is_available", True),
            cost=getattr(obj, "cost", AmenityCost.FREE),
            hours=getattr(obj, "hours", None),
            location=getattr(obj, "location", None),
            icon=getattr(obj, "icon", None),
            tags=getattr(obj, "tags", []) or [],
            details=getattr(obj, "details", {}) or {},
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
    popular_facilities: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    food_drink: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    wellness: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    medical_department: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    front_desk: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    cleaning: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    cleaning_services: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    safety_security: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    recreational_activities: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    public_areas: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    business: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    amenities_for_kids: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    dining: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
    health_wellness: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    sport_fitness: ServiceMatrixGroupRead = Field(
        default_factory=ServiceMatrixGroupRead
    )
    transport: ServiceMatrixGroupRead = Field(default_factory=ServiceMatrixGroupRead)
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
            popular_facilities=ServiceMatrixGroupRead.from_obj(
                obj.get("popular_facilities"), locale
            ),
            food_drink=ServiceMatrixGroupRead.from_obj(obj.get("food_drink"), locale),
            wellness=ServiceMatrixGroupRead.from_obj(obj.get("wellness"), locale),
            medical_department=ServiceMatrixGroupRead.from_obj(
                obj.get("medical_department"), locale
            ),
            transport=ServiceMatrixGroupRead.from_obj(obj.get("transport"), locale),
            front_desk=ServiceMatrixGroupRead.from_obj(obj.get("front_desk"), locale),
            cleaning=ServiceMatrixGroupRead.from_obj(obj.get("cleaning"), locale),
            cleaning_services=ServiceMatrixGroupRead.from_obj(
                obj.get("cleaning_services"), locale
            ),
            safety_security=ServiceMatrixGroupRead.from_obj(
                obj.get("safety_security"), locale
            ),
            recreational_activities=ServiceMatrixGroupRead.from_obj(
                obj.get("recreational_activities"), locale
            ),
            public_areas=ServiceMatrixGroupRead.from_obj(
                obj.get("public_areas"), locale
            ),
            business=ServiceMatrixGroupRead.from_obj(obj.get("business"), locale),
            amenities_for_kids=ServiceMatrixGroupRead.from_obj(
                obj.get("amenities_for_kids"), locale
            ),
            dining=ServiceMatrixGroupRead.from_obj(obj.get("dining"), locale),
            health_wellness=ServiceMatrixGroupRead.from_obj(
                obj.get("health_wellness"), locale
            ),
            sport_fitness=ServiceMatrixGroupRead.from_obj(
                obj.get("sport_fitness"), locale
            ),
            parking=ServiceMatrixGroupRead.from_obj(obj.get("parking"), locale),
            internet=ServiceMatrixGroupRead.from_obj(obj.get("internet"), locale),
            children=ServiceMatrixGroupRead.from_obj(obj.get("children"), locale),
            accessibility=ServiceMatrixGroupRead.from_obj(
                obj.get("accessibility"), locale
            ),
            languages=obj.get("languages") or [],
            notes=pick_locale(obj.get("notes", {}) or {}, locale),
        )
