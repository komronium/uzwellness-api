"""Replace the public sanatorium catalog with six curated Uzbek sanatoriums.

Usage:
    uv run python -m scripts.seed_six_sanatoriums
    uv run python -m scripts.seed_six_sanatoriums --write --confirm-delete-all-sanatoriums
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta, time
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models.amenity import (
    Amenity,
    AmenityCost,
    AmenityScope,
    AmenitySelectionStatus,
    RoomAmenity,
    SanatoriumAmenity,
)
from app.models.availability import RoomAvailability
from app.models.booking import Booking
from app.models.extra_bed import ExtraBedConfig
from app.models.package import Package, PackageItem, PackageItemType
from app.models.program import (
    TreatmentFocus,
    TreatmentGuestApplicability,
    TreatmentProgram,
    TreatmentProgramType,
    TreatmentStayPackageKind,
)
from app.models.promotion import (
    Promotion,
    PromotionAudience,
    PromotionCancellationPolicyMode,
    PromotionCategory,
    PromotionStatus,
)
from app.models.rate_plan import (
    BoardType,
    ConfirmationType,
    PaymentTiming,
    RatePlan,
    RatePlanDateRule,
)
from app.models.region import Region
from app.models.review import ReviewReplyStatus, ReviewSource, SanatoriumReview
from app.models.room import (
    AccommodationType,
    Room,
    RoomImage,
    RoomPricePeriod,
    RoomSizePolicy,
    RoomView,
    SmokingPolicy,
    WindowPolicy,
)
from app.models.sanatorium import (
    HostType,
    PropertyType,
    Sanatorium,
    SanatoriumImage,
    SanatoriumStatus,
    WellnessCategory,
)
from app.models.stay_option import SanatoriumStayOptionPrice, StayOptionGuestType
from app.schemas.room import BeddingOption, RoomFeatures
from app.schemas.sanatorium_policies import SanatoriumPolicies


CATALOG_SOURCE_NOTE = (
    "Seeded as a curated UzWellness demo catalog. Medical focus and location are "
    "based on public sanatorium directory descriptions; prices, availability, "
    "room inventory, reviews, and photos are demonstration data."
)


def tr(en: str, uz: str | None = None, ru: str | None = None) -> dict[str, str]:
    return {"en": en, "uz": uz or en, "ru": ru or en}


def money(value: str | int) -> Decimal:
    return Decimal(str(value))


ROOM_FEATURES = {
    "has_window": True,
    "bathroom": {
        "private": True,
        "type": "shower",
        "toiletries": True,
        "hairdryer": True,
        "slippers": True,
    },
    "climate": {
        "air_conditioning": True,
        "heating": True,
    },
    "kitchen": {"refrigerator": True, "kettle": True},
    "safety": {"safe": True, "smoke_detector": True},
    "entertainment": {"tv": True, "satellite_channels": True},
    "comfort": {
        "desk": True,
        "carpet": True,
    },
    "highlights": ["private bathroom", "Wi-Fi", "diet meals"],
}
ROOM_FEATURES = RoomFeatures.model_validate(ROOM_FEATURES).model_dump(mode="json")

BEDS: dict[str, list[dict[str, Any]]] = {
    "single": [{"label": "1 single bed", "beds": [{"type": "single", "count": 1}]}],
    "twin": [{"label": "2 single beds", "beds": [{"type": "single", "count": 2}]}],
    "double": [{"label": "1 double bed", "beds": [{"type": "double", "count": 1}]}],
    "family": [
        {
            "label": "1 double bed and 2 single beds",
            "beds": [
                {"type": "double", "count": 1},
                {"type": "single", "count": 2},
            ],
        }
    ],
}
for bed_options in BEDS.values():
    for bed_option in bed_options:
        BeddingOption.model_validate(bed_option)

IMAGE_BANK = {
    "chortoq": [
        "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1576013551627-0cc20b96c2a7?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=1600&q=80",
    ],
    "sitorai": [
        "https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1584132967334-10e028bd69f7?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1600&q=80",
    ],
    "zomin": [
        "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1519821172141-b5d8b3d2f175?auto=format&fit=crop&w=1600&q=80",
    ],
    "oqtosh": [
        "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1445019980597-93fa8acb246c?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=1600&q=80",
    ],
    "chinobod": [
        "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1551927411-95e412943b58?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1596178065887-1198b6148b2b?auto=format&fit=crop&w=1600&q=80",
    ],
    "chimyon": [
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1521401830884-6c03c1c87ebb?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1600&q=80",
    ],
}


AMENITIES = [
    ("mineral_water", "Mineral water", "medical", AmenityScope.BOTH, "droplets"),
    (
        "doctor_consultation",
        "Doctor consultation",
        "medical",
        AmenityScope.BOTH,
        "stethoscope",
    ),
    ("physiotherapy", "Physiotherapy", "medical", AmenityScope.BOTH, "activity"),
    (
        "lab_diagnostics",
        "Diagnostics lab",
        "medical",
        AmenityScope.SANATORIUM,
        "microscope",
    ),
    ("therapeutic_baths", "Therapeutic baths", "medical", AmenityScope.BOTH, "waves"),
    ("pool_access", "Pool access", "wellness", AmenityScope.BOTH, "waves"),
    ("sauna", "Sauna", "wellness", AmenityScope.BOTH, "flame"),
    ("diet_meals", "Diet meals", "food", AmenityScope.BOTH, "utensils"),
    ("wifi", "Wi-Fi", "room", AmenityScope.BOTH, "wifi"),
    ("parking", "Parking", "transport", AmenityScope.SANATORIUM, "parking-circle"),
    ("transfer", "Transfer desk", "transport", AmenityScope.SANATORIUM, "bus"),
    ("mountain_air", "Mountain air", "location", AmenityScope.SANATORIUM, "mountain"),
    ("garden", "Walking garden", "wellness", AmenityScope.SANATORIUM, "trees"),
    ("kids_corner", "Children corner", "family", AmenityScope.SANATORIUM, "baby"),
]

FOCUSES = [
    ("digestive_health", "Digestive health", "gastroenterology"),
    ("musculoskeletal", "Musculoskeletal recovery", "joints and spine"),
    ("cardiovascular", "Cardiovascular recovery", "heart and vessels"),
    ("neurology", "Neurology", "nervous system recovery"),
    ("respiratory", "Respiratory health", "lungs and clean air"),
    ("metabolic_health", "Metabolic health", "endocrine and metabolism"),
    ("urology", "Urology", "kidney and urinary tract care"),
    ("stress_recovery", "Stress recovery", "sleep and nervous system balance"),
]

SANATORIUMS: list[dict[str, Any]] = [
    {
        "slug": "chortoq-sanatoriyasi",
        "image_key": "chortoq",
        "name": tr("Chortoq Sanatorium", "Chortoq sanatoriyasi", "Санаторий Чартак"),
        "city": "Chortoq",
        "region": (
            "namangan",
            "Namangan Region",
            "Namangan viloyati",
            "Наманганская область",
        ),
        "address": tr(
            "Chortoq district, Namangan Region, Uzbekistan",
            "Namangan viloyati, Chortoq tumani, O'zbekiston",
            "Наманганская область, Чартакский район, Узбекистан",
        ),
        "lat": "41.071000",
        "lng": "71.824000",
        "website": "https://www.chortoqsan.uz/",
        "stars": 3,
        "year_opened": 1976,
        "renovation_year": 2023,
        "focuses": ["digestive_health", "musculoskeletal", "cardiovascular"],
        "description": tr(
            "Mineral-water sanatorium for digestive, musculoskeletal, and recovery treatment.",
            "Ovqat hazm qilish, tayanch-harakat va tiklanish davolashiga yo'naltirilgan mineral suv sanatoriysi.",
            "Минеральный санаторий для лечения органов пищеварения, опорно-двигательной системы и восстановления.",
        ),
        "highlights": [
            "mineral drinking cure",
            "hydrotherapy",
            "diet meals",
            "quiet park",
        ],
        "base_price": 620000,
        "rating": "8.8",
    },
    {
        "slug": "sitorai-mohi-hosa-sanatoriyasi",
        "image_key": "sitorai",
        "name": tr(
            "Sitorai Mohi Hosa Sanatorium",
            "Sitorai Mohi Hosa sanatoriyasi",
            "Санаторий Ситораи Мохи Хоса",
        ),
        "city": "Bukhara",
        "region": ("bukhara", "Bukhara Region", "Buxoro viloyati", "Бухарская область"),
        "address": tr(
            "Sitorai Mohi Hosa area, Bukhara Region, Uzbekistan",
            "Buxoro viloyati, Sitorai Mohi Hosa hududi, O'zbekiston",
            "Бухарская область, район Ситораи Мохи Хоса, Узбекистан",
        ),
        "lat": "39.814000",
        "lng": "64.422000",
        "website": None,
        "stars": 3,
        "year_opened": 1985,
        "renovation_year": 2022,
        "focuses": ["urology", "metabolic_health", "digestive_health"],
        "description": tr(
            "Bukhara wellness sanatorium with mineral-water, urology, and metabolic recovery programs.",
            "Mineral suv, urologiya va modda almashinuvi tiklanish dasturlariga ega Buxoro sanatoriysi.",
            "Бухарский санаторий с минеральной водой, урологическими и обменными программами.",
        ),
        "highlights": [
            "mineral baths",
            "urology programs",
            "Bukhara climate",
            "diet meals",
        ],
        "base_price": 540000,
        "rating": "8.6",
    },
    {
        "slug": "zomin-sanatoriyasi",
        "image_key": "zomin",
        "name": tr("Zomin Sanatorium", "Zomin sanatoriyasi", "Санаторий Заамин"),
        "city": "Zomin",
        "region": (
            "jizzakh",
            "Jizzakh Region",
            "Jizzax viloyati",
            "Джизакская область",
        ),
        "address": tr(
            "Zomin mountain area, Jizzakh Region, Uzbekistan",
            "Jizzax viloyati, Zomin tog' hududi, O'zbekiston",
            "Джизакская область, горная зона Заамина, Узбекистан",
        ),
        "lat": "39.960000",
        "lng": "68.395000",
        "website": None,
        "stars": 3,
        "year_opened": 1978,
        "renovation_year": 2021,
        "focuses": ["respiratory", "neurology", "stress_recovery"],
        "description": tr(
            "Mountain-climate sanatorium for respiratory recovery, sleep balance, and rehabilitation.",
            "Nafas yo'llari, uyqu muvozanati va reabilitatsiya uchun tog' iqlimi sanatoriysi.",
            "Горноклиматический санаторий для дыхательной системы, восстановления сна и реабилитации.",
        ),
        "highlights": [
            "mountain air",
            "walking routes",
            "respiratory programs",
            "pine forest",
        ],
        "base_price": 580000,
        "rating": "8.9",
    },
    {
        "slug": "oqtosh-sanatoriyasi",
        "image_key": "oqtosh",
        "name": tr("Oq-Tosh Sanatorium", "Oq-Tosh sanatoriyasi", "Санаторий Акташ"),
        "city": "Bostanliq",
        "region": (
            "tashkent-region",
            "Tashkent Region",
            "Toshkent viloyati",
            "Ташкентская область",
        ),
        "address": tr(
            "Oq-Tosh mountain area, Bostanliq district, Tashkent Region, Uzbekistan",
            "Toshkent viloyati, Bo'stonliq tumani, Oq-Tosh tog' hududi",
            "Ташкентская область, Бостанлыкский район, горная зона Акташ",
        ),
        "lat": "41.620000",
        "lng": "69.930000",
        "website": None,
        "stars": 3,
        "year_opened": 1980,
        "renovation_year": 2020,
        "focuses": ["respiratory", "cardiovascular", "stress_recovery"],
        "description": tr(
            "Mountain wellness sanatorium near Tashkent for respiratory and cardiovascular recovery.",
            "Toshkent yaqinidagi nafas yo'llari va yurak-qon tomir tiklanishiga mos tog' sanatoriysi.",
            "Горный санаторий недалеко от Ташкента для дыхательной и сердечно-сосудистой реабилитации.",
        ),
        "highlights": [
            "mountain climate",
            "short transfer from Tashkent",
            "sauna",
            "walking garden",
        ],
        "base_price": 650000,
        "rating": "8.7",
    },
    {
        "slug": "chinobod-sanatoriyasi",
        "image_key": "chinobod",
        "name": tr("Chinobod Sanatorium", "Chinobod sanatoriyasi", "Санаторий Чинабад"),
        "city": "Tashkent",
        "region": (
            "tashkent-city",
            "Tashkent City",
            "Toshkent shahri",
            "город Ташкент",
        ),
        "address": tr(
            "Chinobod area, Tashkent, Uzbekistan",
            "Toshkent shahri, Chinobod hududi, O'zbekiston",
            "город Ташкент, район Чинабад, Узбекистан",
        ),
        "lat": "41.366000",
        "lng": "69.314000",
        "website": None,
        "stars": 4,
        "year_opened": 1972,
        "renovation_year": 2024,
        "focuses": ["cardiovascular", "neurology", "metabolic_health"],
        "description": tr(
            "Urban sanatorium in Tashkent with diagnostics, physiotherapy, and recovery programs.",
            "Diagnostika, fizioterapiya va tiklanish dasturlariga ega Toshkent shahar sanatoriysi.",
            "Городской санаторий в Ташкенте с диагностикой, физиотерапией и программами восстановления.",
        ),
        "highlights": [
            "city access",
            "diagnostics",
            "physiotherapy",
            "business-friendly stay",
        ],
        "base_price": 720000,
        "rating": "8.5",
    },
    {
        "slug": "chimyon-sanatoriyasi",
        "image_key": "chimyon",
        "name": tr("Chimyon Sanatorium", "Chimyon sanatoriyasi", "Санаторий Чимион"),
        "city": "Fergana",
        "region": (
            "fergana",
            "Fergana Region",
            "Farg'ona viloyati",
            "Ферганская область",
        ),
        "address": tr(
            "Chimyon settlement, Fergana Region, Uzbekistan",
            "Farg'ona viloyati, Chimyon shaharchasi, O'zbekiston",
            "Ферганская область, поселок Чимион, Узбекистан",
        ),
        "lat": "40.189000",
        "lng": "71.772000",
        "website": None,
        "stars": 3,
        "year_opened": 1979,
        "renovation_year": 2022,
        "focuses": ["musculoskeletal", "urology", "digestive_health"],
        "description": tr(
            "Fergana Valley mineral-water sanatorium for joints, urology, and digestive recovery.",
            "Bo'g'imlar, urologiya va hazm tizimini tiklashga yo'naltirilgan Farg'ona vodiysi mineral suv sanatoriysi.",
            "Минеральный санаторий Ферганской долины для суставов, урологии и пищеварительной системы.",
        ),
        "highlights": [
            "mineral springs",
            "therapeutic baths",
            "valley climate",
            "family rooms",
        ],
        "base_price": 560000,
        "rating": "8.6",
    },
]


async def main() -> None:
    args = parse_args()
    async with SessionLocal() as db:
        stats = await replace_catalog(db)
        if args.write:
            if not args.confirm_delete_all_sanatoriums:
                raise SystemExit(
                    "Refusing to write. Pass --confirm-delete-all-sanatoriums."
                )
            await db.commit()
            action = "Seeded"
        else:
            await db.rollback()
            action = "Dry run complete; rolled back"
    print(
        f"{action}: deleted {stats['deleted_bookings']} booking(s), "
        f"{stats['deleted_sanatoriums']} sanatorium(s), "
        f"created {stats['created_sanatoriums']} sanatoriums, "
        f"{stats['created_rooms']} rooms, {stats['created_programs']} programs, "
        f"{stats['created_packages']} packages."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist changes. Without this flag the script rolls back.",
    )
    parser.add_argument(
        "--confirm-delete-all-sanatoriums",
        action="store_true",
        help="Required with --write because the script deletes all sanatoriums.",
    )
    return parser.parse_args()


async def replace_catalog(db: AsyncSession) -> dict[str, int]:
    deleted_bookings = await db.scalar(select(func.count()).select_from(Booking))
    deleted_count = await db.scalar(select(func.count()).select_from(Sanatorium))

    await db.execute(delete(Booking))
    await db.execute(delete(Package))
    await db.execute(delete(Sanatorium))
    await db.flush()

    amenities = await upsert_amenities(db)
    focuses = await upsert_focuses(db)

    stats = {
        "deleted_bookings": int(deleted_bookings or 0),
        "deleted_sanatoriums": int(deleted_count or 0),
        "created_sanatoriums": 0,
        "created_rooms": 0,
        "created_programs": 0,
        "created_packages": 0,
    }
    for display_order, item in enumerate(SANATORIUMS, start=1):
        sanatorium = await create_sanatorium(db, item, display_order)
        await attach_sanatorium_amenities(db, sanatorium, amenities, item)
        await create_sanatorium_images(db, sanatorium, item)
        programs = await create_programs(db, sanatorium, focuses, amenities, item)
        rooms = await create_rooms(db, sanatorium, amenities, item)
        await create_stay_option_prices(db, sanatorium, item)
        await create_extra_beds(db, sanatorium)
        await create_promotions(db, sanatorium)
        await create_reviews(db, sanatorium, rooms, item)
        await create_package(db, sanatorium, rooms[1], item)

        stats["created_sanatoriums"] += 1
        stats["created_rooms"] += len(rooms)
        stats["created_programs"] += len(programs)
        stats["created_packages"] += 1
    return stats


async def upsert_amenities(db: AsyncSession) -> dict[str, Amenity]:
    codes = [item[0] for item in AMENITIES]
    existing = await db.scalars(select(Amenity).where(Amenity.code.in_(codes)))
    by_code = {item.code: item for item in existing if item.code}

    for order, (code, name, category, scope, icon) in enumerate(AMENITIES, start=1):
        amenity = by_code.get(code)
        if amenity is None:
            amenity = Amenity(code=code)
            db.add(amenity)
            by_code[code] = amenity
        amenity.name = tr(name)
        amenity.description = tr(f"{name} is available for this stay.")
        amenity.category = category
        amenity.scope = scope
        amenity.icon = icon
        amenity.display_order = order
        amenity.is_active = True
    await db.flush()
    return by_code


async def upsert_focuses(db: AsyncSession) -> dict[str, TreatmentFocus]:
    slugs = [item[0] for item in FOCUSES]
    existing = await db.scalars(
        select(TreatmentFocus).where(TreatmentFocus.slug.in_(slugs))
    )
    by_slug = {item.slug: item for item in existing}

    for order, (slug, name, desc) in enumerate(FOCUSES, start=1):
        focus = by_slug.get(slug)
        if focus is None:
            focus = TreatmentFocus(slug=slug)
            db.add(focus)
            by_slug[slug] = focus
        focus.name = tr(name)
        focus.description = tr(desc)
        focus.icon = slug.replace("_", "-")
        focus.display_order = order
        focus.is_active = True
    await db.flush()
    return by_slug


async def create_sanatorium(
    db: AsyncSession, item: dict[str, Any], display_order: int
) -> Sanatorium:
    region = await upsert_region(db, item)

    sanatorium = Sanatorium(
        slug=item["slug"],
        name=item["name"],
        description=item["description"],
        city=item["city"],
        region_id=region.id,
        address=item["address"],
        lat=money(item["lat"]),
        lng=money(item["lng"]),
        phones=[],
        postal_code=None,
        customer_support_email=None,
        website=item["website"],
        check_in_time=time(12, 0),
        check_out_time=time(10, 0),
        pets_allowed=False,
        service_animals_allowed=False,
        min_checkin_age=16,
        quiet_hours_from=time(22, 0),
        quiet_hours_to=time(7, 0),
        payment_methods=["cash", "uzcard", "humo", "bank_transfer"],
        house_rules=house_rules(),
        cancellation_policy=cancellation_policy(),
        reservation_auto_confirmation_enabled=True,
        reservation_fallback_processing_method="email",
        reservation_fallback_contact_name=f"{item['name']['en']} booking office",
        reservation_fallback_contact=None,
        weekly_schedule=weekly_schedule(),
        stars=item["stars"],
        property_type=PropertyType.SANATORIUM,
        wellness_category=WellnessCategory.SPA_RESORT,
        treatment_focuses=item["focuses"],
        treatment_profile=treatment_profile(item),
        year_opened=item["year_opened"],
        renovation_year=item["renovation_year"],
        chain_name=None,
        host_type=HostType.PROFESSIONAL_HOST,
        languages_spoken=["uz", "ru", "en"],
        highlights=item["highlights"],
        is_featured=True,
        display_order=display_order * 10,
        promo_badges=promo_badges(),
        surroundings=surroundings(item),
        venues=venues(item),
        meal_schedule=meal_schedule(),
        service_matrix=service_matrix(item),
        medical_base=medical_base(item),
        policies=policies(),
        platform_commission_percent=money("12.00"),
        b2b_commission_percent=money("8.00"),
        agent_discount_tiers=[
            {"min_bookings": 1, "discount_percent": "3.00"},
            {"min_bookings": 10, "discount_percent": "5.00"},
        ],
        avg_rating=money(item["rating"]),
        review_count=2,
        rating_breakdown={
            "cleanliness": 9,
            "amenities": 8,
            "location": 9,
            "service": 9,
            "treatment": 9,
            "food": 8,
        },
        status=SanatoriumStatus.APPROVED,
    )
    db.add(sanatorium)
    await db.flush()
    return sanatorium


async def upsert_region(db: AsyncSession, item: dict[str, Any]) -> Region:
    slug, en, uz, ru = item["region"]
    region = await db.scalar(select(Region).where(Region.slug == slug))
    if region is None:
        region = Region(slug=slug)
        db.add(region)
    region.name = tr(en, uz, ru)
    region.is_active = True
    await db.flush()
    return region


async def attach_sanatorium_amenities(
    db: AsyncSession,
    sanatorium: Sanatorium,
    amenities: dict[str, Amenity],
    item: dict[str, Any],
) -> None:
    codes = [
        "doctor_consultation",
        "physiotherapy",
        "therapeutic_baths",
        "diet_meals",
        "wifi",
        "parking",
        "garden",
    ]
    if "mountain" in " ".join(item["highlights"]):
        codes.append("mountain_air")
    if "mineral" in item["description"]["en"].lower():
        codes.insert(0, "mineral_water")
    if "diagnostics" in item["description"]["en"].lower():
        codes.append("lab_diagnostics")
    codes.extend(["pool_access", "sauna", "transfer"])

    seen: set[str] = set()
    for order, code in enumerate(
        [c for c in codes if not (c in seen or seen.add(c))], start=1
    ):
        db.add(
            SanatoriumAmenity(
                sanatorium_id=sanatorium.id,
                amenity_id=amenities[code].id,
                cost=AmenityCost.FREE,
                is_available=True,
                status=AmenitySelectionStatus.YES,
                details={},
                display_order=order,
            )
        )


async def create_sanatorium_images(
    db: AsyncSession, sanatorium: Sanatorium, item: dict[str, Any]
) -> None:
    for order, url in enumerate(IMAGE_BANK[item["image_key"]], start=1):
        db.add(
            SanatoriumImage(
                sanatorium_id=sanatorium.id,
                url=url,
                order=order,
                is_primary=order == 1,
                category=["exterior", "wellness", "room"][order - 1],
                caption=f"{item['name']['en']} photo {order}",
                caption_i18n=tr(f"{item['name']['en']} photo {order}"),
                alt_text=tr(f"{item['name']['en']} wellness stay"),
                tags=["sanatorium", item["city"].lower(), item["image_key"]],
            )
        )


async def create_programs(
    db: AsyncSession,
    sanatorium: Sanatorium,
    focuses: dict[str, TreatmentFocus],
    amenities: dict[str, Amenity],
    item: dict[str, Any],
) -> list[TreatmentProgram]:
    program_specs = [
        {
            "name": "Basic Cure",
            "kind": TreatmentStayPackageKind.TREATMENT,
            "focus": item["focuses"][0],
            "description": "1 medical examination, 6 medical procedures, access to wellness",
            "exam": 1,
            "procedures": 6,
            "price": "0",
            "services": ["doctor consultation", "6 procedures", "pool access"],
            "default": True,
        },
        {
            "name": "Intensive Recovery",
            "kind": TreatmentStayPackageKind.TREATMENT,
            "focus": item["focuses"][1],
            "description": "1 medical examination, 10 medical procedures, mineral-water or physiotherapy course",
            "exam": 1,
            "procedures": 10,
            "price": "420000",
            "services": ["doctor supervision", "10 procedures", "physiotherapy"],
            "default": False,
        },
        {
            "name": "Pool and Wellness Access",
            "kind": TreatmentStayPackageKind.SPECIAL,
            "focus": item["focuses"][-1],
            "description": "pool access, sauna entry, walking garden access",
            "exam": 0,
            "procedures": 0,
            "price": "140000",
            "services": ["pool", "sauna", "wellness zone"],
            "default": True,
        },
    ]
    programs: list[TreatmentProgram] = []
    for order, spec in enumerate(program_specs, start=1):
        program = TreatmentProgram(
            sanatorium_id=sanatorium.id,
            focus_id=focuses[spec["focus"]].id,
            name=tr(f"{item['name']['en']} {spec['name']}"),
            description=tr(spec["description"]),
            program_type=TreatmentProgramType.STAY_PACKAGE,
            stay_package_kind=spec["kind"],
            guest_applicability=TreatmentGuestApplicability.ALL,
            min_nights=2,
            max_nights=None,
            duration_minutes=None,
            price=money(spec["price"]),
            currency="UZS",
            instructor_name=None,
            instructor_bio={},
            group_size_min=None,
            group_size_max=None,
            what_to_bring=tr("Comfortable clothing and personal medical documents."),
            medical_exam_count=spec["exam"],
            medical_procedure_count=spec["procedures"],
            drink_cure_included="mineral" in spec["description"],
            sauna_entries=1 if "sauna" in spec["description"] else None,
            pool_access_included=True,
            included_services=spec["services"],
            is_active=True,
            is_default_stay_package=spec["default"],
            display_order=order,
        )
        program.amenities = [
            amenities["doctor_consultation"],
            amenities["physiotherapy"],
            amenities["pool_access"],
        ]
        db.add(program)
        programs.append(program)
    await db.flush()
    return programs


async def create_rooms(
    db: AsyncSession,
    sanatorium: Sanatorium,
    amenities: dict[str, Amenity],
    item: dict[str, Any],
) -> list[Room]:
    base = int(item["base_price"])
    room_specs = [
        ("Standard Single", "single", 1, 1, 0, 14, base, 8),
        ("Comfort Twin", "twin", 2, 2, 1, 22, int(base * 1.45), 10),
        ("Family Suite", "family", 4, 3, 2, 38, int(base * 2.20), 12),
    ]
    rooms: list[Room] = []
    for order, (
        name,
        bed_key,
        capacity,
        adults,
        children,
        size,
        price,
        inv,
    ) in enumerate(room_specs, start=1):
        room = Room(
            sanatorium_id=sanatorium.id,
            name=tr(name),
            description=tr(
                f"{name} at {item['name']['en']} with private bathroom, Wi-Fi, and treatment access."
            ),
            size_sqm=size,
            room_size_policy=RoomSizePolicy.SAME_SIZE,
            floor="1-3",
            beds=BEDS[bed_key],
            view=RoomView.MOUNTAIN
            if "mountain" in " ".join(item["highlights"])
            else RoomView.GARDEN,
            smoking_allowed=False,
            smoking_policy=SmokingPolicy.NON_SMOKING,
            window_policy=WindowPolicy.ALL_ROOMS_HAVE_WINDOWS,
            window_description="Exterior window with natural light.",
            room_features=ROOM_FEATURES,
            accommodation_type=AccommodationType.HOTEL_ROOM,
            capacity=capacity,
            max_adults=adults,
            max_children=children,
            max_child_rate_children=children,
            inventory_count=inv,
            room_advisories=[],
            base_price=money(price),
            base_price_weekend=money(int(price * 1.08)),
            base_currency="UZS",
            markup_percent=money("0"),
            discount_percent=money("0"),
            min_nights=2,
            is_active=True,
            display_order=order,
        )
        db.add(room)
        await db.flush()
        await create_room_images(db, room, item, name)
        await attach_room_amenities(db, room, amenities)
        await create_room_calendar(db, room)
        await create_rate_plans(db, room)
        rooms.append(room)
    return rooms


async def create_room_images(
    db: AsyncSession, room: Room, item: dict[str, Any], room_name: str
) -> None:
    urls = IMAGE_BANK[item["image_key"]]
    for order, url in enumerate([urls[2], urls[1]], start=1):
        db.add(
            RoomImage(
                room_id=room.id,
                url=url,
                order=order,
                is_primary=order == 1,
                category="bedroom",
                caption=f"{room_name} photo {order}",
                caption_i18n=tr(f"{room_name} photo {order}"),
                alt_text=tr(f"{room_name} at {item['name']['en']}"),
                tags=["room", item["slug"]],
            )
        )


async def attach_room_amenities(
    db: AsyncSession, room: Room, amenities: dict[str, Amenity]
) -> None:
    for order, code in enumerate(
        ["wifi", "diet_meals", "doctor_consultation"], start=1
    ):
        db.add(
            RoomAmenity(
                room_id=room.id,
                amenity_id=amenities[code].id,
                status=AmenitySelectionStatus.YES,
                cost=AmenityCost.FREE,
                is_available=True,
                details={},
                display_order=order,
            )
        )


async def create_room_calendar(db: AsyncSession, room: Room) -> None:
    today = date.today()
    db.add(
        RoomPricePeriod(
            room_id=room.id,
            label="2026 wellness season",
            date_from=today,
            date_to=today + timedelta(days=210),
            base_price=room.base_price,
            base_price_weekend=room.base_price_weekend,
            discount_percent=room.discount_percent,
        )
    )
    for offset in range(180):
        day = today + timedelta(days=offset)
        db.add(
            RoomAvailability(
                room_id=room.id,
                date=day,
                units_blocked=1 if day.weekday() in {5, 6} and offset % 17 == 0 else 0,
                units_booked=1 if offset % 13 == 0 else 0,
            )
        )


async def create_rate_plans(db: AsyncSession, room: Room) -> None:
    specs = [
        ("Full board and treatment", BoardType.FULL_BOARD, "0", 2),
        ("Half board and treatment", BoardType.HALF_BOARD, "-8", 2),
    ]
    today = date.today()
    for name, board, adjustment, min_nights in specs:
        rate_plan = RatePlan(
            room_id=room.id,
            name=tr(name),
            board=board,
            refundable=True,
            free_cancellation_days=3,
            cancellation_penalty_percent=money("30.00"),
            payment_timing=PaymentTiming.AT_HOTEL,
            confirmation=ConfirmationType.INSTANT,
            price_adjustment_percent=money(adjustment),
            promo_label=None,
            promo_percent=None,
            promo_starts_at=None,
            promo_ends_at=None,
            min_nights=min_nights,
            max_nights=None,
            is_active=True,
        )
        db.add(rate_plan)
        await db.flush()
        for offset in range(180):
            day = today + timedelta(days=offset)
            db.add(
                RatePlanDateRule(
                    rate_plan_id=rate_plan.id,
                    date=day,
                    selling_rate=room.base_price_weekend
                    if day.weekday() in {5, 6}
                    else room.base_price,
                    is_closed=False,
                    min_advance_hours=12,
                    max_advance_hours=24 * 180,
                    min_stay_nights=min_nights,
                    min_stay_arrival_nights=min_nights,
                )
            )


async def create_stay_option_prices(
    db: AsyncSession, sanatorium: Sanatorium, item: dict[str, Any]
) -> None:
    deltas = [
        (StayOptionGuestType.ADULT, BoardType.FULL_BOARD, True, 180000),
        (StayOptionGuestType.ADULT, BoardType.HALF_BOARD, True, 120000),
        (StayOptionGuestType.ADULT, BoardType.FULL_BOARD, False, 90000),
        (StayOptionGuestType.ADULT, BoardType.HALF_BOARD, False, 60000),
        (StayOptionGuestType.CHILD, BoardType.FULL_BOARD, True, 120000),
        (StayOptionGuestType.CHILD, BoardType.HALF_BOARD, True, 80000),
        (StayOptionGuestType.CHILD, BoardType.FULL_BOARD, False, 60000),
        (StayOptionGuestType.CHILD, BoardType.HALF_BOARD, False, 40000),
    ]
    for guest_type, board, treatment_included, delta in deltas:
        db.add(
            SanatoriumStayOptionPrice(
                sanatorium_id=sanatorium.id,
                guest_type=guest_type,
                board=board,
                treatment_included=treatment_included,
                price_delta=money(delta),
                currency="UZS",
                is_available=True,
            )
        )


async def create_extra_beds(db: AsyncSession, sanatorium: Sanatorium) -> None:
    db.add_all(
        [
            ExtraBedConfig(
                sanatorium_id=sanatorium.id,
                name=tr("Extra bed", "Qo'shimcha karavot", "Дополнительная кровать"),
                description=tr("Portable extra bed with linen."),
                price_per_night=money("70000"),
                currency="UZS",
                max_count=8,
                is_active=True,
            ),
            ExtraBedConfig(
                sanatorium_id=sanatorium.id,
                name=tr("Baby crib", "Bolalar krovatkasi", "Детская кроватка"),
                description=tr("Baby crib for children up to 4 years old."),
                price_per_night=money("0"),
                currency="UZS",
                max_count=4,
                is_active=True,
            ),
        ]
    )


async def create_promotions(db: AsyncSession, sanatorium: Sanatorium) -> None:
    today = date.today()
    db.add(
        Promotion(
            sanatorium_id=sanatorium.id,
            name=tr("Long-stay wellness discount"),
            category=PromotionCategory.LONG_STAY,
            status=PromotionStatus.ACTIVE,
            discount_percent=money("7.00"),
            booking_date_from=today,
            booking_date_to=today + timedelta(days=180),
            stay_date_from=today,
            stay_date_to=today + timedelta(days=240),
            booking_weekdays=[0, 1, 2, 3, 4, 5, 6],
            stay_weekdays=[0, 1, 2, 3, 4, 5, 6],
            audience=PromotionAudience.ALL_GUESTS,
            cancellation_policy_mode=PromotionCancellationPolicyMode.ORIGINAL,
        )
    )


async def create_reviews(
    db: AsyncSession,
    sanatorium: Sanatorium,
    rooms: list[Room],
    item: dict[str, Any],
) -> None:
    reviews = [
        (
            "Dilshod",
            "Uzbekistan",
            "family",
            round(float(item["rating"])),
            "Clean rooms, calm territory, and clear treatment schedule.",
        ),
        (
            "Natalia",
            "Kazakhstan",
            "couple",
            round(min(9.4, float(item["rating"]) + 0.2)),
            "Good doctors and useful procedures. Meals are simple but balanced.",
        ),
    ]
    for order, (name, country, traveler_type, rating, body) in enumerate(
        reviews, start=1
    ):
        db.add(
            SanatoriumReview(
                sanatorium_id=sanatorium.id,
                room_id=rooms[min(order - 1, len(rooms) - 1)].id,
                source=ReviewSource.UZWELLNESS,
                external_id=f"{item['slug']}-{order}",
                reviewer_name=name,
                reviewer_country=country,
                traveler_type=traveler_type,
                language="en",
                stayed_at=date.today() - timedelta(days=30 * order),
                stayed_room_name=rooms[min(order - 1, len(rooms) - 1)].name["en"],
                rating=rating,
                score_label="Excellent" if rating >= Decimal("9") else "Very good",
                cleanliness=9,
                amenities=8,
                location=9,
                service=9,
                treatment=9,
                value=8,
                food=8,
                body=body,
                translated_body=None,
                positive_tags=["treatment", "cleanliness", "location"],
                negative_tags=[],
                photos=[{"url": IMAGE_BANK[item["image_key"]][1]}],
                reply_body="Thank you for your review. We are glad the treatment plan was useful.",
                reply_language="en",
                reply_status=ReviewReplyStatus.REPLIED,
                is_visible=True,
            )
        )


async def create_package(
    db: AsyncSession,
    sanatorium: Sanatorium,
    room: Room,
    item: dict[str, Any],
) -> None:
    package = Package(
        slug=f"{item['slug']}-7-night-recovery",
        title=tr(f"{item['name']['en']} 7-night recovery package"),
        description=tr(
            "Seven nights with accommodation, full board, treatment package, and transfer help."
        ),
        hero_image_url=IMAGE_BANK[item["image_key"]][0],
        duration_nights=7,
        base_price=money(int(item["base_price"]) * 7),
        currency="UZS",
        sanatorium_id=sanatorium.id,
        room_id=room.id,
        is_active=True,
        is_featured=True,
        display_order=sanatorium.display_order,
    )
    db.add(package)
    await db.flush()
    db.add_all(
        [
            PackageItem(
                package_id=package.id,
                item_type=PackageItemType.TREATMENT,
                title=tr("Basic cure package"),
                description=tr("Doctor consultation and daily procedures."),
                is_included=True,
                display_order=1,
            ),
            PackageItem(
                package_id=package.id,
                item_type=PackageItemType.MEAL,
                title=tr("Full board diet meals"),
                description=tr("Three balanced meals per day."),
                is_included=True,
                display_order=2,
            ),
            PackageItem(
                package_id=package.id,
                item_type=PackageItemType.TRANSFER,
                title=tr("Transfer assistance"),
                description=tr(
                    "Arrival transfer can be arranged by the booking office."
                ),
                is_included=False,
                extra_price=money("250000"),
                display_order=3,
            ),
        ]
    )


def house_rules() -> dict[str, Any]:
    return tr(
        "Check-in is from 12:00, check-out is until 10:00. Rooms are non-smoking. Passport and relevant medical documents are required.",
        "Kirish 12:00 dan, chiqish 10:00 gacha. Xonalarda chekish mumkin emas. Pasport va tegishli tibbiy hujjatlar talab qilinadi.",
        "Заезд с 12:00, выезд до 10:00. Курение в номерах запрещено. Требуются паспорт и медицинские документы.",
    )


def cancellation_policy() -> dict[str, Any]:
    return tr(
        "Free cancellation is available up to 3 days before arrival. Later cancellation may be charged 30%.",
        "Kelishdan 3 kun oldingacha bepul bekor qilish mumkin. Keyin bekor qilish uchun 30% jarima qo'llanishi mumkin.",
        "Бесплатная отмена доступна за 3 дня до заезда. Поздняя отмена может удерживаться в размере 30%.",
    )


def promo_badges() -> list[dict[str, Any]]:
    return [
        {
            "code": "free_cancellation",
            "kind": "benefit",
            "title": tr("Free cancellation", "Bepul bekor qilish", "Бесплатная отмена"),
            "description": tr("Cancel free up to 3 days before arrival."),
            "icon": "calendar-x",
            "is_active": True,
            "priority": 10,
        },
        {
            "code": "treatment_packages",
            "kind": "medical",
            "title": tr("Treatment packages", "Davolash paketlari", "Лечебные пакеты"),
            "description": tr("Doctor consultation and procedures are available."),
            "icon": "stethoscope",
            "is_active": True,
            "priority": 20,
        },
        {
            "code": "instant_confirmation",
            "kind": "booking",
            "title": tr(
                "Instant confirmation",
                "Tezkor tasdiqlash",
                "Мгновенное подтверждение",
            ),
            "description": tr("Room offers can be booked instantly."),
            "icon": "badge-check",
            "is_active": True,
            "priority": 30,
        },
    ]


def weekly_schedule() -> dict[str, Any]:
    return {
        day: {"open": "08:00", "close": "20:00"}
        for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    }


def meal_schedule() -> list[dict[str, str]]:
    return [
        {
            "meal": "breakfast",
            "time_from": "08:00",
            "time_to": "09:30",
            "style": "diet buffet",
        },
        {
            "meal": "lunch",
            "time_from": "13:00",
            "time_to": "14:30",
            "style": "diet menu",
        },
        {
            "meal": "dinner",
            "time_from": "18:30",
            "time_to": "20:00",
            "style": "diet menu",
        },
    ]


def treatment_profile(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": item["description"],
        "main_focuses": item["focuses"],
        "source_note": CATALOG_SOURCE_NOTE,
        "doctor_required": True,
        "min_recommended_nights": 7,
    }


def surroundings(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": tr("Walking area"), "distance_m": 150, "type": "nature"},
        {"name": tr(f"{item['city']} center"), "distance_m": 4500, "type": "city"},
    ]


def venues(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": tr("Medical block"), "type": "medical", "capacity": 80},
        {"name": tr("Dining hall"), "type": "restaurant", "capacity": 120},
        {"name": tr("Wellness zone"), "type": "wellness", "capacity": 35},
    ]


def service_matrix(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "medical_services": {
            "included": [
                "doctor consultation",
                "physiotherapy",
                "therapeutic baths",
            ],
            "paid": ["advanced diagnostics", "additional procedures"],
        },
        "guest_services": {
            "included": ["Wi-Fi", "parking", "walking garden"],
            "paid": ["transfer", "extra bed", "laundry"],
        },
    }


def medical_base(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "focuses": item["focuses"],
        "equipment": [
            "physiotherapy room",
            "therapeutic bath room",
            "massage room",
            "doctor consultation office",
        ],
        "contraindications": [
            "acute infectious disease",
            "uncontrolled hypertension",
            "doctor restriction for spa procedures",
        ],
    }


def policies() -> dict[str, Any]:
    payload = {
        "check_in": {
            "instructions": tr(
                "Passport and medical documents are required at check-in."
            ),
            "required_documents": ["passport", "medical documents"],
            "latest_check_in_time": "22:00",
            "earliest_check_out_time": "07:00",
            "front_desk_available": True,
            "front_desk_24h": False,
            "front_desk_opens_at": "08:00",
            "front_desk_closes_at": "20:00",
        },
        "important_notices": {
            "items": [
                {
                    "title": tr("Doctor consultation required"),
                    "body": tr(
                        "Treatment procedures are assigned after a doctor consultation."
                    ),
                    "category": "medical",
                }
            ]
        },
        "children": {
            "allowed": True,
            "min_age": 0,
            "treatment_min_age": 12,
            "child_rate_mode": "standard",
            "child_rates_prepaid": True,
            "existing_bed_price_bands": [
                {
                    "min_age": 0,
                    "max_age": 5,
                    "pricing_method": "free",
                    "price_per_night": "0",
                    "currency": "UZS",
                    "notes": tr("Free when sharing existing bed."),
                },
                {
                    "min_age": 6,
                    "max_age": 11,
                    "pricing_method": "fixed",
                    "price_per_night": "180000",
                    "currency": "UZS",
                    "notes": tr("Child meal and stay supplement."),
                },
            ],
        },
        "extra_bed": {
            "available": True,
            "crib_available": True,
            "price": "70000",
            "currency": "UZS",
            "age_price_bands": [
                {
                    "min_age": 4,
                    "max_age": None,
                    "price_per_night": "70000",
                    "currency": "UZS",
                    "includes": ["linen"],
                    "notes": tr("Portable extra bed with linen."),
                }
            ],
        },
        "breakfast": {
            "included": True,
            "available": True,
            "style": "diet buffet",
            "serving_style": "buffet",
            "cuisine": "uzbek wellness",
            "hours": "08:00-09:30",
            "hours_by_weekday": {
                day: "08:00-09:30"
                for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            },
        },
        "pets": {
            "allowed": False,
            "service_animals_allowed": False,
            "advance_notice_required": False,
        },
        "cancellation": {
            "free_cancellation_until_days_before": 3,
            "penalty_percent": "30.00",
        },
        "deposit": {
            "required": False,
            "percent": "0",
            "currency": "UZS",
            "type": "none",
        },
        "payment": {
            "methods": ["cash", "uzcard", "humo", "bank_transfer"],
            "deposit_required": False,
            "deposit_percent": "0",
            "guarantee_methods": ["phone confirmation"],
            "accepted_cards": ["uzcard", "humo"],
        },
        "fees": {
            "pricing_mode": "tax_inclusive",
            "tax_rules": [],
            "mandatory_fees": [],
            "optional_fees": ["transfer", "extra bed", "laundry"],
        },
        "reservation_restrictions": {
            "cutoff_hours_before_check_in": 12,
            "min_advance_hours": 12,
            "max_advance_days": 180,
        },
    }
    return SanatoriumPolicies.model_validate(payload).model_dump(mode="json")


if __name__ == "__main__":
    asyncio.run(main())
