import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.core.utils import pick_locale
from app.models.sanatorium import PropertyType, WellnessCategory
from app.schemas.common import Page


class FeaturedSanatoriumCard(BaseModel):
    sanatorium_id: uuid.UUID
    sanatorium_slug: str
    sanatorium_name: str
    city: str
    region_id: uuid.UUID | None
    region_name: str | None
    destination_id: uuid.UUID | None
    destination_name: str | None
    primary_image_url: str | None
    photos_count: int
    stars: int
    avg_rating: Decimal | None
    review_count: int
    property_type: PropertyType
    wellness_category: WellnessCategory | None
    treatment_focuses: list[str]
    min_price: Decimal | None
    min_price_currency: str | None
    min_price_usd: Decimal | None
    is_featured: bool
    display_order: int

    @classmethod
    def from_obj(
        cls,
        obj,
        *,
        locale: str,
        min_price: Decimal | None,
        min_price_currency: str | None,
        min_price_usd: Decimal | None,
    ) -> "FeaturedSanatoriumCard":
        return cls(
            sanatorium_id=obj.id,
            sanatorium_slug=obj.slug,
            sanatorium_name=pick_locale(obj.name, locale),
            city=obj.city,
            region_id=obj.region_id,
            region_name=(
                pick_locale(obj.region.name, locale) if obj.region is not None else None
            ),
            destination_id=obj.destination_id,
            destination_name=(
                pick_locale(obj.destination.name, locale)
                if obj.destination is not None
                else None
            ),
            primary_image_url=_primary_image_url(obj.images),
            photos_count=len(obj.images or []),
            stars=obj.stars,
            avg_rating=obj.avg_rating,
            review_count=obj.review_count,
            property_type=obj.property_type,
            wellness_category=obj.wellness_category,
            treatment_focuses=obj.treatment_focuses,
            min_price=min_price,
            min_price_currency=min_price_currency,
            min_price_usd=min_price_usd,
            is_featured=obj.is_featured,
            display_order=obj.display_order,
        )


class FeaturedSanatoriumList(Page[FeaturedSanatoriumCard]):
    pass


def _primary_image_url(images) -> str | None:
    if not images:
        return None
    primary = next((image for image in images if image.is_primary), None)
    return (primary or images[0]).url
