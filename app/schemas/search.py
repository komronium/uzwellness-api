import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.sanatorium import PropertyType, WellnessCategory
from app.schemas.common import Page


class StaySearchItem(BaseModel):
    sanatorium_id: uuid.UUID
    sanatorium_slug: str
    sanatorium_name: str
    city: str
    region_id: uuid.UUID | None
    region_name: str | None
    primary_image_url: str | None
    stars: int
    avg_rating: Decimal | None
    review_count: int
    property_type: PropertyType
    wellness_category: WellnessCategory | None
    treatment_focuses: list[str]
    check_in: date
    check_out: date
    nights: int
    adults: int
    children: int
    guests: int
    available_room_id: uuid.UUID
    available_room_name: str
    rooms_count_needed: int
    min_total_price: Decimal
    min_total_price_currency: str
    min_total_price_usd: Decimal | None
    min_total_price_display: Decimal | None = None
    display_currency: str | None = None


class StaySearchList(Page[StaySearchItem]):
    pass
