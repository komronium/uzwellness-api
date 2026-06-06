"""Seed one real sanatorium with rich admin/demo content.

Usage:
    uv run python -m scripts.seed_real_sanatorium
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta, time
from decimal import Decimal
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.image_processing import WEBP_MIME, to_webp
from app.core.storage import get_storage
from app.models.amenity import (
    Amenity,
    AmenityCost,
    AmenityScope,
    AmenitySelectionStatus,
    RoomAmenity,
    SanatoriumAmenity,
)
from app.models.availability import RoomAvailability
from app.models.destination import Destination
from app.models.extra_bed import ExtraBedConfig
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

SLUG = "chortoq-sanatoriyasi"
OFFICIAL_SITE = "https://www.chortoqsan.uz/"
IMAGE_BASE = "https://www.chortoqsan.uz/images"
IMAGE_TIMEOUT_SECONDS = 30


def tr(en: str, uz: str | None = None, ru: str | None = None) -> dict[str, str]:
    return {"en": en, "uz": uz or en, "ru": ru or en}


async def main() -> None:
    async with SessionLocal() as db:
        sanatorium = await seed_chortoq_sanatorium(db)
        await db.commit()
        print(f"Seeded {sanatorium.slug}: {sanatorium.id}")


async def seed_chortoq_sanatorium(db: AsyncSession) -> Sanatorium:
    region = await upsert_region(db)
    destination = await upsert_destination(db)
    sanatorium = await upsert_sanatorium(db, region, destination)
    await refresh_related_content(db, sanatorium)

    amenities = await upsert_amenities(db)
    await attach_sanatorium_amenities(db, sanatorium, amenities)
    sanatorium_image_urls = await save_images(SANATORIUM_IMAGES)
    await create_sanatorium_images(db, sanatorium, sanatorium_image_urls)

    focuses = await upsert_treatment_focuses(db)
    programs = await create_treatment_programs(db, sanatorium, focuses, amenities)
    rooms = await create_rooms(db, sanatorium, amenities)

    await create_room_rate_plans(db, rooms, amenities)
    await create_stay_option_prices(db, sanatorium)
    await create_extra_beds(db, sanatorium)
    await create_promotions(db, sanatorium)
    await create_reviews(db, sanatorium, rooms, sanatorium_image_urls)

    treatment_profile = dict(sanatorium.treatment_profile)
    treatment_profile["stay_packages"] = [
        {
            "name": program.name,
            "kind": program.stay_package_kind,
            "guest_applicability": program.guest_applicability,
            "price": str(program.price or Decimal("0")),
            "currency": program.currency,
        }
        for program in programs
        if program.program_type == TreatmentProgramType.STAY_PACKAGE
    ]
    sanatorium.treatment_profile = treatment_profile
    return sanatorium


async def upsert_region(db: AsyncSession) -> Region:
    region = await db.scalar(select(Region).where(Region.slug == "namangan"))
    if region is None:
        region = Region(
            slug="namangan",
            name=tr("Namangan Region", "Namangan viloyati", "Наманганская область"),
            is_active=True,
        )
        db.add(region)
        await db.flush()
    return region


async def upsert_destination(db: AsyncSession) -> Destination:
    destination = await db.scalar(
        select(Destination).where(Destination.slug == "namangan-mineral-springs")
    )
    if destination is None:
        destination = Destination(slug="namangan-mineral-springs")
        db.add(destination)

    destination.name = tr(
        "Namangan Mineral Springs",
        "Namangan mineral buloqlari",
        "Минеральные источники Намангана",
    )
    destination.tagline = tr(
        "Mineral-water therapy in the Fergana Valley",
        "Farg'ona vodiysida mineral suv bilan davolanish",
        "Минеральное лечение в Ферганской долине",
    )
    destination.description = tr(
        "Curated sanatoriums around Chortoq and nearby mineral-water areas.",
        "Chortoq va yaqin mineral hududlardagi sanatoriyalar.",
        "Санатории Чартака и близлежащих минеральных зон.",
    )
    destination.hero_image_url = f"{IMAGE_BASE}/84.jpg"
    destination.lat = Decimal("41.071000")
    destination.lng = Decimal("71.824000")
    destination.is_active = True
    await db.flush()
    return destination


async def upsert_sanatorium(
    db: AsyncSession, region: Region, destination: Destination
) -> Sanatorium:
    sanatorium = await db.scalar(select(Sanatorium).where(Sanatorium.slug == SLUG))
    if sanatorium is None:
        sanatorium = Sanatorium(slug=SLUG)
        db.add(sanatorium)

    sanatorium.name = tr(
        "Chortoq Sanatorium",
        "Chortoq sanatoriyasi",
        "Санаторий Чартак",
    )
    sanatorium.description = tr(
        "A mineral-water sanatorium in Namangan Region focused on restorative "
        "treatment, physiotherapy, hydrotherapy, diet meals, and quiet recreation.",
        "Namangan viloyatidagi mineral suv sanatoriysi. Qayta tiklovchi davolash, "
        "fizioterapiya, gidroterapiya, parhez ovqatlanish va sokin dam olishga "
        "moslashgan.",
        "Минеральный санаторий в Наманганской области для восстановительного "
        "лечения, физиотерапии, гидротерапии, диетического питания и отдыха.",
    )
    sanatorium.city = "Chortoq"
    sanatorium.region_id = region.id
    sanatorium.destination_id = destination.id
    sanatorium.address = tr(
        "Chortoq district, Namangan Region, Uzbekistan",
        "Namangan viloyati, Chortoq tumani, O'zbekiston",
        "Узбекистан, Наманганская область, Чартакский район",
    )
    sanatorium.lat = Decimal("41.071000")
    sanatorium.lng = Decimal("71.824000")
    sanatorium.phones = [
        {"label": "Reception", "phone": "+998 69 433 10 00"},
        {"label": "Booking", "phone": "+998 90 213 10 00"},
    ]
    sanatorium.postal_code = "160800"
    sanatorium.customer_support_email = "info@chortoqsan.uz"
    sanatorium.website = OFFICIAL_SITE
    sanatorium.check_in_time = time(12, 0)
    sanatorium.check_out_time = time(10, 0)
    sanatorium.pets_allowed = False
    sanatorium.service_animals_allowed = False
    sanatorium.min_checkin_age = 16
    sanatorium.quiet_hours_from = time(22, 0)
    sanatorium.quiet_hours_to = time(7, 0)
    sanatorium.payment_methods = ["cash", "uzcard", "humo", "bank_transfer"]
    sanatorium.house_rules = HOUSE_RULES
    sanatorium.cancellation_policy = CANCELLATION_POLICY
    sanatorium.reservation_auto_confirmation_enabled = True
    sanatorium.reservation_fallback_processing_method = "email"
    sanatorium.reservation_fallback_contact_name = "Chortoq booking office"
    sanatorium.reservation_fallback_contact = "info@chortoqsan.uz"
    sanatorium.weekly_schedule = WEEKLY_SCHEDULE
    sanatorium.stars = 3
    sanatorium.property_type = PropertyType.SANATORIUM
    sanatorium.wellness_category = WellnessCategory.SPA_RESORT
    sanatorium.treatment_focuses = [
        "digestive_health",
        "musculoskeletal",
        "cardiovascular",
        "stress_recovery",
    ]
    sanatorium.treatment_profile = TREATMENT_PROFILE.copy()
    sanatorium.year_opened = 1976
    sanatorium.renovation_year = 2023
    sanatorium.chain_name = None
    sanatorium.host_type = HostType.PROFESSIONAL_HOST
    sanatorium.languages_spoken = ["uz", "ru", "en"]
    sanatorium.highlights = HIGHLIGHTS
    sanatorium.is_featured = True
    sanatorium.display_order = 40
    sanatorium.promo_badges = PROMO_BADGES
    sanatorium.surroundings = SURROUNDINGS
    sanatorium.venues = VENUES
    sanatorium.meal_schedule = MEAL_SCHEDULE
    sanatorium.service_matrix = SERVICE_MATRIX
    sanatorium.medical_base = MEDICAL_BASE
    sanatorium.policies = POLICIES
    sanatorium.platform_commission_percent = Decimal("12.00")
    sanatorium.b2b_commission_percent = Decimal("8.00")
    sanatorium.agent_discount_tiers = [
        {"min_bookings": 1, "discount_percent": "3.00"},
        {"min_bookings": 10, "discount_percent": "5.00"},
    ]
    sanatorium.avg_rating = Decimal("8.80")
    sanatorium.review_count = 6
    sanatorium.rating_breakdown = {
        "cleanliness": 9,
        "amenities": 8,
        "location": 9,
        "service": 9,
        "treatment": 9,
        "food": 8,
    }
    sanatorium.status = SanatoriumStatus.APPROVED
    await db.flush()
    return sanatorium


async def refresh_related_content(db: AsyncSession, sanatorium: Sanatorium) -> None:
    await db.execute(delete(Promotion).where(Promotion.sanatorium_id == sanatorium.id))
    await db.execute(
        delete(SanatoriumStayOptionPrice).where(
            SanatoriumStayOptionPrice.sanatorium_id == sanatorium.id
        )
    )
    await db.execute(
        delete(ExtraBedConfig).where(ExtraBedConfig.sanatorium_id == sanatorium.id)
    )
    await db.execute(
        delete(TreatmentProgram).where(TreatmentProgram.sanatorium_id == sanatorium.id)
    )
    await db.execute(
        delete(SanatoriumReview).where(SanatoriumReview.sanatorium_id == sanatorium.id)
    )
    await db.execute(
        delete(SanatoriumImage).where(SanatoriumImage.sanatorium_id == sanatorium.id)
    )
    await db.execute(
        delete(SanatoriumAmenity).where(
            SanatoriumAmenity.sanatorium_id == sanatorium.id
        )
    )
    await db.execute(delete(Room).where(Room.sanatorium_id == sanatorium.id))
    await db.flush()


async def upsert_amenities(db: AsyncSession) -> dict[str, Amenity]:
    existing = await db.scalars(select(Amenity).where(Amenity.code.in_(AMENITY_CODES)))
    amenities = {amenity.code: amenity for amenity in existing if amenity.code}

    for order, item in enumerate(AMENITY_DATA, start=1):
        amenity = amenities.get(item["code"])
        if amenity is None:
            amenity = Amenity(code=item["code"])
            db.add(amenity)
            amenities[item["code"]] = amenity
        amenity.name = tr(item["name"], item.get("uz"), item.get("ru"))
        amenity.description = tr(item["description"])
        amenity.category = item["category"]
        amenity.scope = item["scope"]
        amenity.icon = item["icon"]
        amenity.display_order = order
        amenity.is_active = True

    await db.flush()
    return amenities


async def attach_sanatorium_amenities(
    db: AsyncSession, sanatorium: Sanatorium, amenities: dict[str, Amenity]
) -> None:
    for order, code in enumerate(SANATORIUM_AMENITY_CODES, start=1):
        db.add(
            SanatoriumAmenity(
                sanatorium_id=sanatorium.id,
                amenity_id=amenities[code].id,
                cost=SANATORIUM_PAID_AMENITIES.get(code, AmenityCost.FREE),
                is_available=True,
                status=AmenitySelectionStatus.YES,
                details=SANATORIUM_AMENITY_DETAILS.get(code, {}),
                display_order=order,
            )
        )
    await db.flush()


async def upsert_treatment_focuses(db: AsyncSession) -> dict[str, TreatmentFocus]:
    slugs = [item["slug"] for item in FOCUS_DATA]
    existing = await db.scalars(
        select(TreatmentFocus).where(TreatmentFocus.slug.in_(slugs))
    )
    focuses = {focus.slug: focus for focus in existing}

    for order, item in enumerate(FOCUS_DATA, start=1):
        focus = focuses.get(item["slug"])
        if focus is None:
            focus = TreatmentFocus(slug=item["slug"])
            db.add(focus)
            focuses[item["slug"]] = focus
        focus.name = tr(item["name"], item["uz"], item["ru"])
        focus.description = tr(item["description"])
        focus.icon = item["icon"]
        focus.display_order = order
        focus.is_active = True
    await db.flush()
    return focuses


async def create_treatment_programs(
    db: AsyncSession,
    sanatorium: Sanatorium,
    focuses: dict[str, TreatmentFocus],
    amenities: dict[str, Amenity],
) -> list[TreatmentProgram]:
    created: list[TreatmentProgram] = []
    for order, item in enumerate(TREATMENT_PROGRAMS, start=1):
        program = TreatmentProgram(
            sanatorium_id=sanatorium.id,
            focus_id=focuses[item["focus"]].id,
            name=tr(item["name"], item["uz"], item["ru"]),
            description=tr(item["description"]),
            program_type=item["program_type"],
            stay_package_kind=item["kind"],
            guest_applicability=item["guest_applicability"],
            min_nights=item.get("min_nights"),
            max_nights=item.get("max_nights"),
            duration_minutes=item.get("duration_minutes"),
            price=Decimal(item["price"]),
            currency="UZS",
            instructor_name=item.get("instructor_name"),
            instructor_bio=tr(item.get("instructor_bio", "")),
            group_size_min=item.get("group_size_min"),
            group_size_max=item.get("group_size_max"),
            what_to_bring=tr("Comfortable clothing and personal medical documents."),
            medical_exam_count=item.get("medical_exam_count", 0),
            medical_procedure_count=item.get("medical_procedure_count", 0),
            drink_cure_included=item.get("drink_cure_included", False),
            sauna_entries=item.get("sauna_entries"),
            pool_access_included=item.get("pool_access_included", False),
            included_services=item["included_services"],
            is_active=True,
            is_default_stay_package=item.get("default", False),
            display_order=order,
        )
        program.amenities = [amenities[code] for code in item["amenities"]]
        db.add(program)
        created.append(program)
    await db.flush()
    return created


async def create_rooms(
    db: AsyncSession, sanatorium: Sanatorium, amenities: dict[str, Amenity]
) -> list[Room]:
    saved_images = await save_images(ROOM_IMAGES)
    rooms: list[Room] = []

    for order, item in enumerate(ROOM_DATA, start=1):
        room = Room(
            sanatorium_id=sanatorium.id,
            name=tr(item["name"], item["uz"], item["ru"]),
            description=tr(item["description"]),
            size_sqm=item["size_sqm"],
            room_size_policy=RoomSizePolicy.SAME_SIZE,
            floor=item["floor"],
            beds=item["beds"],
            view=item["view"],
            smoking_allowed=False,
            smoking_policy=SmokingPolicy.NON_SMOKING,
            window_policy=WindowPolicy.ALL_ROOMS_HAVE_WINDOWS,
            window_description="All rooms have exterior windows.",
            room_features=item["room_features"],
            accommodation_type=AccommodationType.HOTEL_ROOM,
            capacity=item["capacity"],
            max_adults=item["max_adults"],
            max_children=item["max_children"],
            max_child_rate_children=item["max_child_rate_children"],
            inventory_count=item["inventory_count"],
            room_advisories=item["room_advisories"],
            base_price=Decimal(item["base_price"]),
            base_price_weekend=Decimal(item["base_price_weekend"]),
            base_currency="UZS",
            markup_percent=Decimal("0"),
            discount_percent=Decimal(item["discount_percent"]),
            min_nights=item["min_nights"],
            is_active=True,
            display_order=order,
        )
        db.add(room)
        await db.flush()

        for image_order, image_key in enumerate(item["images"], start=1):
            image_url = saved_images[image_key]
            db.add(
                RoomImage(
                    room_id=room.id,
                    url=image_url,
                    order=image_order,
                    is_primary=image_order == 1,
                    category="bedroom",
                    caption=f"{item['name']} photo {image_order}",
                    caption_i18n=tr(f"{item['name']} photo {image_order}"),
                    alt_text=tr(f"{item['name']} at Chortoq Sanatorium"),
                    tags=["room", item["code"]],
                )
            )

        for amenity_order, code in enumerate(item["amenities"], start=1):
            db.add(
                RoomAmenity(
                    room_id=room.id,
                    amenity_id=amenities[code].id,
                    status=AmenitySelectionStatus.YES,
                    cost=AmenityCost.FREE,
                    is_available=True,
                    details={},
                    display_order=amenity_order,
                )
            )

        await create_room_calendar(db, room)
        rooms.append(room)

    await db.flush()
    return rooms


async def create_room_calendar(db: AsyncSession, room: Room) -> None:
    today = date.today()
    db.add(
        RoomPricePeriod(
            room_id=room.id,
            label="2026 health season",
            date_from=today,
            date_to=today + timedelta(days=180),
            base_price=room.base_price,
            base_price_weekend=room.base_price_weekend,
            discount_percent=room.discount_percent,
        )
    )

    for offset in range(120):
        day = today + timedelta(days=offset)
        units_blocked = 1 if day.weekday() in {4, 5} and offset % 11 == 0 else 0
        units_booked = 1 if offset % 9 == 0 else 0
        db.add(
            RoomAvailability(
                room_id=room.id,
                date=day,
                units_blocked=units_blocked,
                units_booked=units_booked,
            )
        )


async def create_room_rate_plans(
    db: AsyncSession, rooms: list[Room], amenities: dict[str, Amenity]
) -> None:
    today = date.today()
    for room in rooms:
        for item in RATE_PLAN_DATA:
            rate_plan = RatePlan(
                room_id=room.id,
                name=tr(item["name"], item["uz"], item["ru"]),
                board=item["board"],
                refundable=item["refundable"],
                free_cancellation_days=item["free_cancellation_days"],
                cancellation_penalty_percent=Decimal(item["penalty_percent"]),
                payment_timing=item["payment_timing"],
                confirmation=item["confirmation"],
                price_adjustment_percent=Decimal(item["price_adjustment_percent"]),
                promo_label=item.get("promo_label"),
                promo_percent=(
                    Decimal(item["promo_percent"])
                    if item.get("promo_percent")
                    else None
                ),
                promo_starts_at=None,
                promo_ends_at=None,
                min_nights=item["min_nights"],
                max_nights=item.get("max_nights"),
                is_active=True,
            )
            rate_plan.amenities = [amenities[code] for code in item["amenities"]]
            db.add(rate_plan)
            await db.flush()

            for offset in range(120):
                day = today + timedelta(days=offset)
                is_weekend = day.weekday() in {4, 5}
                selling_rate = (
                    room.base_price_weekend if is_weekend else room.base_price
                )
                db.add(
                    RatePlanDateRule(
                        rate_plan_id=rate_plan.id,
                        date=day,
                        selling_rate=selling_rate,
                        is_closed=False,
                        min_advance_hours=12,
                        max_advance_hours=24 * 180,
                        min_stay_nights=room.min_nights,
                        min_stay_arrival_nights=room.min_nights,
                    )
                )


async def create_stay_option_prices(db: AsyncSession, sanatorium: Sanatorium) -> None:
    prices = [
        (StayOptionGuestType.ADULT, BoardType.FULL_BOARD, True, "180000"),
        (StayOptionGuestType.ADULT, BoardType.HALF_BOARD, True, "120000"),
        (StayOptionGuestType.ADULT, BoardType.FULL_BOARD, False, "90000"),
        (StayOptionGuestType.ADULT, BoardType.HALF_BOARD, False, "60000"),
        (StayOptionGuestType.CHILD, BoardType.FULL_BOARD, True, "120000"),
        (StayOptionGuestType.CHILD, BoardType.HALF_BOARD, True, "85000"),
        (StayOptionGuestType.CHILD, BoardType.FULL_BOARD, False, "60000"),
        (StayOptionGuestType.CHILD, BoardType.HALF_BOARD, False, "40000"),
    ]
    for guest_type, board, treatment_included, delta in prices:
        db.add(
            SanatoriumStayOptionPrice(
                sanatorium_id=sanatorium.id,
                guest_type=guest_type,
                board=board,
                treatment_included=treatment_included,
                price_delta=Decimal(delta),
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
                price_per_night=Decimal("70000"),
                currency="UZS",
                max_count=8,
                is_active=True,
            ),
            ExtraBedConfig(
                sanatorium_id=sanatorium.id,
                name=tr("Baby crib", "Bolalar krovatkasi", "Детская кроватка"),
                description=tr("Baby crib for children up to 4 years old."),
                price_per_night=Decimal("0"),
                currency="UZS",
                max_count=4,
                is_active=True,
            ),
        ]
    )


async def create_promotions(db: AsyncSession, sanatorium: Sanatorium) -> None:
    today = date.today()
    db.add_all(
        [
            Promotion(
                sanatorium_id=sanatorium.id,
                name=tr("Long-stay wellness discount"),
                category=PromotionCategory.LONG_STAY,
                status=PromotionStatus.ACTIVE,
                discount_percent=Decimal("7.00"),
                booking_date_from=today,
                booking_date_to=today + timedelta(days=180),
                stay_date_from=today,
                stay_date_to=today + timedelta(days=240),
                booking_weekdays=[0, 1, 2, 3, 4, 5, 6],
                stay_weekdays=[0, 1, 2, 3, 4, 5, 6],
                audience=PromotionAudience.ALL_GUESTS,
                cancellation_policy_mode=PromotionCancellationPolicyMode.ORIGINAL,
            ),
            Promotion(
                sanatorium_id=sanatorium.id,
                name=tr("Weekday recovery rate"),
                category=PromotionCategory.BASIC_DEAL,
                status=PromotionStatus.ACTIVE,
                discount_percent=Decimal("5.00"),
                booking_date_from=today,
                booking_date_to=today + timedelta(days=90),
                stay_date_from=today,
                stay_date_to=today + timedelta(days=120),
                booking_weekdays=[0, 1, 2, 3, 6],
                stay_weekdays=[0, 1, 2, 3],
                audience=PromotionAudience.ALL_GUESTS,
                cancellation_policy_mode=PromotionCancellationPolicyMode.ORIGINAL,
            ),
        ]
    )


async def create_reviews(
    db: AsyncSession,
    sanatorium: Sanatorium,
    rooms: list[Room],
    sanatorium_image_urls: dict[str, str],
) -> None:
    room_by_name = {room.name["en"]: room for room in rooms}
    for item in REVIEW_DATA:
        db.add(
            SanatoriumReview(
                sanatorium_id=sanatorium.id,
                room_id=room_by_name[item["room"]].id,
                source=item["source"],
                external_id=item["external_id"],
                reviewer_name=item["reviewer_name"],
                reviewer_country=item["reviewer_country"],
                traveler_type=item["traveler_type"],
                language=item["language"],
                stayed_at=item["stayed_at"],
                stayed_room_name=item["room"],
                rating=item["rating"],
                score_label=item["score_label"],
                cleanliness=item["cleanliness"],
                amenities=item["amenities"],
                location=item["location"],
                service=item["service"],
                treatment=item["treatment"],
                value=item["value"],
                food=item["food"],
                body=item["body"],
                translated_body=item.get("translated_body"),
                positive_tags=item["positive_tags"],
                negative_tags=item["negative_tags"],
                photos=[sanatorium_image_urls["mineral_pool"]],
                reply_body=item.get("reply_body"),
                reply_language="en" if item.get("reply_body") else None,
                reply_status=(
                    ReviewReplyStatus.REPLIED
                    if item.get("reply_body")
                    else ReviewReplyStatus.AWAITING_REPLY
                ),
                is_visible=True,
            )
        )


async def create_sanatorium_images(
    db: AsyncSession, sanatorium: Sanatorium, images: dict[str, str]
) -> None:
    for order, item in enumerate(SANATORIUM_IMAGES, start=1):
        db.add(
            SanatoriumImage(
                sanatorium_id=sanatorium.id,
                url=images[item["key"]],
                order=order,
                is_primary=order == 1,
                category=item["category"],
                caption=item["caption"],
                caption_i18n=tr(item["caption"]),
                alt_text=tr(item["alt"]),
                tags=item["tags"],
            )
        )


async def save_images(items: list[dict]) -> dict[str, str]:
    storage = get_storage()
    saved: dict[str, str] = {}
    for item in items:
        content = download_image(item["url"])
        webp, _ = to_webp(content)
        key = f"seed/{SLUG}/{item['key']}.webp"
        saved[item["key"]] = await storage.save(
            key=key, content=webp, content_type=WEBP_MIME
        )
    return saved


def download_image(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; UzWellnessSeeder/1.0; "
                "+https://uzwellness.com)"
            )
        },
    )
    try:
        with urlopen(request, timeout=IMAGE_TIMEOUT_SECONDS) as response:
            return response.read()
    except URLError as exc:
        print(f"Could not download image: {url}", file=sys.stderr)
        raise RuntimeError(f"Image download failed: {url}") from exc


SANATORIUM_IMAGES = [
    {
        "key": "exterior_main",
        "url": f"{IMAGE_BASE}/84.jpg",
        "category": "exterior",
        "caption": "Main sanatorium building",
        "alt": "Chortoq Sanatorium exterior",
        "tags": ["official", "exterior"],
    },
    {
        "key": "garden",
        "url": f"{IMAGE_BASE}/85.jpg",
        "category": "surroundings",
        "caption": "Green walking area",
        "alt": "Walking area at Chortoq Sanatorium",
        "tags": ["official", "garden"],
    },
    {
        "key": "mineral_pool",
        "url": f"{IMAGE_BASE}/86.jpg",
        "category": "treatment",
        "caption": "Mineral-water treatment area",
        "alt": "Mineral-water treatment at Chortoq Sanatorium",
        "tags": ["official", "treatment"],
    },
    {
        "key": "dining",
        "url": f"{IMAGE_BASE}/87.jpg",
        "category": "dining",
        "caption": "Diet dining hall",
        "alt": "Dining hall at Chortoq Sanatorium",
        "tags": ["official", "dining"],
    },
    {
        "key": "medical_base",
        "url": f"{IMAGE_BASE}/98.jpg",
        "category": "medical",
        "caption": "Medical treatment base",
        "alt": "Medical base at Chortoq Sanatorium",
        "tags": ["official", "medical"],
    },
]

ROOM_IMAGES = [
    {"key": "standard_single_1", "url": f"{IMAGE_BASE}/116.jpg"},
    {"key": "standard_single_2", "url": f"{IMAGE_BASE}/117.jpg"},
    {"key": "standard_double_1", "url": f"{IMAGE_BASE}/89.jpg"},
    {"key": "standard_double_2", "url": f"{IMAGE_BASE}/90.jpg"},
    {"key": "superior_twin_1", "url": f"{IMAGE_BASE}/91.jpg"},
    {"key": "superior_twin_2", "url": f"{IMAGE_BASE}/92.jpg"},
    {"key": "family_suite_1", "url": f"{IMAGE_BASE}/93.jpg"},
    {"key": "family_suite_2", "url": f"{IMAGE_BASE}/94.jpg"},
]

AMENITY_DATA = [
    {
        "code": "mineral_water",
        "name": "Mineral water",
        "uz": "Mineral suv",
        "ru": "Минеральная вода",
        "description": "Mineral-water therapy and drinking cure.",
        "category": "health_and_wellness",
        "scope": AmenityScope.SANATORIUM,
        "icon": "droplets",
    },
    {
        "code": "doctor_consultation",
        "name": "Doctor consultation",
        "uz": "Shifokor konsultatsiyasi",
        "ru": "Консультация врача",
        "description": "Initial doctor check and treatment supervision.",
        "category": "health_and_wellness",
        "scope": AmenityScope.SANATORIUM,
        "icon": "stethoscope",
    },
    {
        "code": "physiotherapy",
        "name": "Physiotherapy",
        "uz": "Fizioterapiya",
        "ru": "Физиотерапия",
        "description": "Classic physiotherapy procedures.",
        "category": "health_and_wellness",
        "scope": AmenityScope.SANATORIUM,
        "icon": "activity",
    },
    {
        "code": "hydrotherapy",
        "name": "Hydrotherapy",
        "uz": "Gidroterapiya",
        "ru": "Гидротерапия",
        "description": "Mineral baths and therapeutic showers.",
        "category": "health_and_wellness",
        "scope": AmenityScope.SANATORIUM,
        "icon": "waves",
    },
    {
        "code": "massage",
        "name": "Massage",
        "uz": "Massaj",
        "ru": "Массаж",
        "description": "Manual massage procedures.",
        "category": "health_and_wellness",
        "scope": AmenityScope.SANATORIUM,
        "icon": "hand",
    },
    {
        "code": "sauna",
        "name": "Sauna",
        "uz": "Sauna",
        "ru": "Сауна",
        "description": "Sauna access according to package rules.",
        "category": "health_and_wellness",
        "scope": AmenityScope.SANATORIUM,
        "icon": "flame",
    },
    {
        "code": "diet_meals",
        "name": "Diet meals",
        "uz": "Parhez ovqatlanish",
        "ru": "Диетическое питание",
        "description": "Diet meals aligned with sanatorium treatment.",
        "category": "dining",
        "scope": AmenityScope.SANATORIUM,
        "icon": "utensils",
    },
    {
        "code": "transfer_to_hotel",
        "name": "Transfer to hotel",
        "uz": "Mehmonxonaga transfer",
        "ru": "Трансфер до отеля",
        "description": "Transfer can be arranged by request.",
        "category": "transport",
        "scope": AmenityScope.SANATORIUM,
        "icon": "bus",
    },
    {
        "code": "parking",
        "name": "Parking",
        "uz": "Avtoturargoh",
        "ru": "Парковка",
        "description": "On-site parking.",
        "category": "transport",
        "scope": AmenityScope.SANATORIUM,
        "icon": "parking-circle",
    },
    {
        "code": "wifi",
        "name": "Wi-Fi",
        "uz": "Wi-Fi",
        "ru": "Wi-Fi",
        "description": "Wireless internet.",
        "category": "internet",
        "scope": AmenityScope.BOTH,
        "icon": "wifi",
    },
    {
        "code": "private_bathroom",
        "name": "Private bathroom",
        "uz": "Alohida hammom",
        "ru": "Отдельная ванная",
        "description": "Private in-room bathroom.",
        "category": "bathroom",
        "scope": AmenityScope.ROOM,
        "icon": "bath",
    },
    {
        "code": "air_conditioning",
        "name": "Air conditioning",
        "uz": "Konditsioner",
        "ru": "Кондиционер",
        "description": "In-room air conditioning.",
        "category": "room",
        "scope": AmenityScope.ROOM,
        "icon": "snowflake",
    },
    {
        "code": "tv",
        "name": "TV",
        "uz": "Televizor",
        "ru": "Телевизор",
        "description": "In-room TV.",
        "category": "media",
        "scope": AmenityScope.ROOM,
        "icon": "tv",
    },
    {
        "code": "refrigerator",
        "name": "Refrigerator",
        "uz": "Muzlatkich",
        "ru": "Холодильник",
        "description": "Small in-room refrigerator.",
        "category": "kitchen",
        "scope": AmenityScope.ROOM,
        "icon": "box",
    },
    {
        "code": "balcony",
        "name": "Balcony",
        "uz": "Balkon",
        "ru": "Балкон",
        "description": "Room balcony.",
        "category": "room_layout",
        "scope": AmenityScope.ROOM,
        "icon": "panel-top",
    },
]

AMENITY_CODES = [item["code"] for item in AMENITY_DATA]
SANATORIUM_AMENITY_CODES = [
    "mineral_water",
    "doctor_consultation",
    "physiotherapy",
    "hydrotherapy",
    "massage",
    "sauna",
    "diet_meals",
    "transfer_to_hotel",
    "parking",
    "wifi",
]
SANATORIUM_PAID_AMENITIES = {
    "massage": AmenityCost.PAID,
    "transfer_to_hotel": AmenityCost.ON_REQUEST,
}
SANATORIUM_AMENITY_DETAILS = {
    "mineral_water": {"availability": "daily", "included_in_packages": True},
    "doctor_consultation": {"initial_check": True, "follow_up": "by appointment"},
    "diet_meals": {"meal_count": 3, "diet_table_support": True},
}

FOCUS_DATA = [
    {
        "slug": "digestive-health",
        "name": "Digestive health",
        "uz": "Ovqat hazm qilish salomatligi",
        "ru": "Пищеварение",
        "description": "Mineral-water and diet therapy.",
        "icon": "leaf",
    },
    {
        "slug": "musculoskeletal",
        "name": "Musculoskeletal recovery",
        "uz": "Tayanch-harakat tizimini tiklash",
        "ru": "Опорно-двигательная система",
        "description": "Physiotherapy, hydrotherapy, and massage.",
        "icon": "bone",
    },
    {
        "slug": "cardiovascular",
        "name": "Cardiovascular care",
        "uz": "Yurak-qon tomir parvarishi",
        "ru": "Сердечно-сосудистая система",
        "description": "Gentle recovery under doctor supervision.",
        "icon": "heart-pulse",
    },
    {
        "slug": "stress-recovery",
        "name": "Stress recovery",
        "uz": "Stressdan tiklanish",
        "ru": "Восстановление от стресса",
        "description": "Quiet recreation and light wellness routines.",
        "icon": "sparkles",
    },
]

TREATMENT_PROGRAMS = [
    {
        "name": "Chortoq Basic Cure",
        "uz": "Chortoq Basic Cure",
        "ru": "Базовое лечение Чартак",
        "description": "Doctor check, mineral-water drinking cure, and basic procedures.",
        "focus": "digestive-health",
        "program_type": TreatmentProgramType.STAY_PACKAGE,
        "kind": TreatmentStayPackageKind.TREATMENT,
        "guest_applicability": TreatmentGuestApplicability.ALL,
        "min_nights": 3,
        "price": "0",
        "medical_exam_count": 1,
        "medical_procedure_count": 8,
        "drink_cure_included": True,
        "sauna_entries": 1,
        "pool_access_included": True,
        "included_services": ["doctor check", "drink cure", "8 procedures", "pool"],
        "amenities": ["doctor_consultation", "mineral_water", "hydrotherapy"],
        "default": True,
    },
    {
        "name": "Mineral Water Therapy Plus",
        "uz": "Mineral suv terapiyasi Plus",
        "ru": "Минеральная терапия плюс",
        "description": "Extended mineral-water cure with hydrotherapy and sauna access.",
        "focus": "digestive-health",
        "program_type": TreatmentProgramType.STAY_PACKAGE,
        "kind": TreatmentStayPackageKind.TREATMENT,
        "guest_applicability": TreatmentGuestApplicability.ADULT,
        "min_nights": 5,
        "price": "450000",
        "medical_exam_count": 1,
        "medical_procedure_count": 12,
        "drink_cure_included": True,
        "sauna_entries": 2,
        "pool_access_included": True,
        "included_services": ["doctor check", "drink cure", "12 procedures", "sauna"],
        "amenities": ["doctor_consultation", "mineral_water", "sauna"],
    },
    {
        "name": "Physiotherapy Recovery",
        "uz": "Fizioterapiya orqali tiklanish",
        "ru": "Физиотерапевтическое восстановление",
        "description": "Physiotherapy and massage-focused recovery package.",
        "focus": "musculoskeletal",
        "program_type": TreatmentProgramType.STAY_PACKAGE,
        "kind": TreatmentStayPackageKind.TREATMENT,
        "guest_applicability": TreatmentGuestApplicability.ALL,
        "min_nights": 7,
        "price": "650000",
        "medical_exam_count": 1,
        "medical_procedure_count": 14,
        "drink_cure_included": True,
        "sauna_entries": 1,
        "pool_access_included": True,
        "included_services": ["physiotherapy", "massage", "mineral bath"],
        "amenities": ["physiotherapy", "massage", "hydrotherapy"],
    },
    {
        "name": "Mineral Pool Access",
        "uz": "Mineral basseyn tashrifi",
        "ru": "Посещение минерального бассейна",
        "description": "Special wellness access for guests without treatment package.",
        "focus": "stress-recovery",
        "program_type": TreatmentProgramType.STAY_PACKAGE,
        "kind": TreatmentStayPackageKind.SPECIAL,
        "guest_applicability": TreatmentGuestApplicability.ALL,
        "min_nights": 1,
        "price": "120000",
        "medical_exam_count": 0,
        "medical_procedure_count": 0,
        "drink_cure_included": False,
        "pool_access_included": True,
        "included_services": ["mineral pool access"],
        "amenities": ["hydrotherapy"],
    },
    {
        "name": "Sauna and Wellness Access",
        "uz": "Sauna va wellness tashrifi",
        "ru": "Сауна и wellness доступ",
        "description": "Sauna and light wellness access without medical procedures.",
        "focus": "stress-recovery",
        "program_type": TreatmentProgramType.STAY_PACKAGE,
        "kind": TreatmentStayPackageKind.SPECIAL,
        "guest_applicability": TreatmentGuestApplicability.ALL,
        "min_nights": 1,
        "price": "180000",
        "medical_exam_count": 0,
        "medical_procedure_count": 0,
        "sauna_entries": 1,
        "pool_access_included": True,
        "included_services": ["sauna", "wellness zone"],
        "amenities": ["sauna", "hydrotherapy"],
    },
    {
        "name": "Therapeutic Massage",
        "uz": "Davolovchi massaj",
        "ru": "Лечебный массаж",
        "description": "Single therapeutic massage session.",
        "focus": "musculoskeletal",
        "program_type": TreatmentProgramType.SESSION,
        "kind": TreatmentStayPackageKind.TREATMENT,
        "guest_applicability": TreatmentGuestApplicability.ALL,
        "duration_minutes": 45,
        "price": "150000",
        "included_services": ["manual massage"],
        "amenities": ["massage"],
    },
]

ROOM_DATA = [
    {
        "code": "standard_single",
        "name": "Standard Single Room",
        "uz": "Standart bir kishilik xona",
        "ru": "Стандартный одноместный номер",
        "description": "Compact room for one guest with private bathroom.",
        "size_sqm": 18,
        "floor": "1-3",
        "beds": [{"type": "single", "width_cm": 90, "count": 1}],
        "view": RoomView.GARDEN,
        "room_features": {"windows": "all", "bathroom": "private"},
        "capacity": 1,
        "max_adults": 1,
        "max_children": 0,
        "max_child_rate_children": 0,
        "inventory_count": 12,
        "room_advisories": [],
        "base_price": "520000",
        "base_price_weekend": "590000",
        "discount_percent": "5.00",
        "min_nights": 2,
        "images": ["standard_single_1", "standard_single_2"],
        "amenities": ["wifi", "private_bathroom", "tv", "refrigerator"],
    },
    {
        "code": "standard_double",
        "name": "Standard Double Room",
        "uz": "Standart ikki kishilik xona",
        "ru": "Стандартный двухместный номер",
        "description": "Double room with private bathroom and basic comfort amenities.",
        "size_sqm": 25,
        "floor": "1-4",
        "beds": [{"type": "double", "width_cm": 150, "count": 1}],
        "view": RoomView.COURTYARD,
        "room_features": {"windows": "all", "bathroom": "private"},
        "capacity": 3,
        "max_adults": 2,
        "max_children": 1,
        "max_child_rate_children": 1,
        "inventory_count": 18,
        "room_advisories": [],
        "base_price": "820000",
        "base_price_weekend": "920000",
        "discount_percent": "5.00",
        "min_nights": 2,
        "images": ["standard_double_1", "standard_double_2"],
        "amenities": ["wifi", "private_bathroom", "tv", "refrigerator"],
    },
    {
        "code": "superior_twin",
        "name": "Superior Twin Room",
        "uz": "Superior twin xona",
        "ru": "Улучшенный номер twin",
        "description": "Larger twin room with two single beds and balcony option.",
        "size_sqm": 30,
        "floor": "2-4",
        "beds": [{"type": "single", "width_cm": 90, "count": 2}],
        "view": RoomView.PARK,
        "room_features": {"windows": "all", "bathroom": "private", "balcony": True},
        "capacity": 3,
        "max_adults": 2,
        "max_children": 1,
        "max_child_rate_children": 1,
        "inventory_count": 14,
        "room_advisories": [],
        "base_price": "980000",
        "base_price_weekend": "1100000",
        "discount_percent": "5.00",
        "min_nights": 2,
        "images": ["superior_twin_1", "superior_twin_2"],
        "amenities": [
            "wifi",
            "private_bathroom",
            "tv",
            "refrigerator",
            "air_conditioning",
            "balcony",
        ],
    },
    {
        "code": "family_suite",
        "name": "Family Suite",
        "uz": "Oilaviy lyuks",
        "ru": "Семейный люкс",
        "description": "Suite for family stays with extra space and improved amenities.",
        "size_sqm": 42,
        "floor": "3-4",
        "beds": [
            {"type": "double", "width_cm": 160, "count": 1},
            {"type": "single", "width_cm": 90, "count": 1},
        ],
        "view": RoomView.GARDEN,
        "room_features": {
            "windows": "all",
            "bathroom": "private",
            "sitting_area": True,
        },
        "capacity": 4,
        "max_adults": 3,
        "max_children": 2,
        "max_child_rate_children": 2,
        "inventory_count": 6,
        "room_advisories": [],
        "base_price": "1350000",
        "base_price_weekend": "1500000",
        "discount_percent": "5.00",
        "min_nights": 3,
        "images": ["family_suite_1", "family_suite_2"],
        "amenities": [
            "wifi",
            "private_bathroom",
            "tv",
            "refrigerator",
            "air_conditioning",
        ],
    },
]

RATE_PLAN_DATA = [
    {
        "name": "Full board and treatment",
        "uz": "To'liq pansion va davolanish",
        "ru": "Полный пансион и лечение",
        "board": BoardType.FULL_BOARD,
        "refundable": True,
        "free_cancellation_days": 3,
        "penalty_percent": "30.00",
        "payment_timing": PaymentTiming.AT_HOTEL,
        "confirmation": ConfirmationType.INSTANT,
        "price_adjustment_percent": "0.00",
        "min_nights": 2,
        "amenities": ["diet_meals", "doctor_consultation", "mineral_water"],
    },
    {
        "name": "Half board and treatment",
        "uz": "Yarim pansion va davolanish",
        "ru": "Полупансион и лечение",
        "board": BoardType.HALF_BOARD,
        "refundable": True,
        "free_cancellation_days": 3,
        "penalty_percent": "30.00",
        "payment_timing": PaymentTiming.AT_HOTEL,
        "confirmation": ConfirmationType.INSTANT,
        "price_adjustment_percent": "-5.00",
        "min_nights": 2,
        "amenities": ["diet_meals", "doctor_consultation", "mineral_water"],
    },
]

WEEKLY_SCHEDULE = {
    "front_desk": {"mode": "24_7"},
    "medical_department": {
        "mon_fri": "08:00-17:00",
        "sat": "08:00-13:00",
        "sun": "doctor_on_duty",
    },
    "meal_times": {"breakfast": "08:00", "lunch": "13:00", "dinner": "18:30"},
    "weekend_days": ["friday", "saturday"],
}

HOUSE_RULES = {
    "front_desk": "24/7",
    "quiet_hours": "22:00-07:00",
    "smoking": "Non-smoking rooms; smoking only in designated outdoor zones.",
    "documents_required": ["passport", "medical notes if available"],
}

CANCELLATION_POLICY = {
    "type": "flexible",
    "free_cancellation_until_days_before_arrival": 3,
    "penalty": "30% of first night after free cancellation period",
}

POLICIES = {
    "check_in": {"from": "12:00", "until": "23:59"},
    "check_out": {"until": "10:00"},
    "children": {
        "allowed": True,
        "child_rate_mode": "standard",
        "rates": [
            {"age_to": 4, "price": "free"},
            {"age_from": 5, "price": "same_as_adult"},
        ],
    },
    "extra_beds": {"available": True, "cribs_available": True},
    "breakfast": {"available": True, "serving_style": "buffet_and_set_menu"},
    "pets": {"allowed": False},
    "deposits": {"required": False},
    "taxes": [
        {
            "type": "vat",
            "method": "included",
            "amount_percent": "12.00",
            "validity": "indefinite",
        },
        {
            "type": "tourism_fee",
            "method": "included",
            "amount": "0",
            "validity": "indefinite",
        },
    ],
    "reservation_restrictions": {
        "min_advance_hours": 12,
        "max_advance_days": 180,
        "min_length_of_stay": 2,
    },
}

TREATMENT_PROFILE = {
    "doctor_supervision": True,
    "medical_license": "local",
    "main_natural_factor": "mineral_water",
    "procedure_categories": [
        "hydrotherapy",
        "physiotherapy",
        "massage",
        "diet_therapy",
        "drinking_cure",
    ],
    "contraindications_note": "Procedures are assigned after doctor consultation.",
}

HIGHLIGHTS = [
    "Mineral-water treatment",
    "Diet meals",
    "Quiet Chortoq location",
    "Doctor-supervised programs",
    "Weekend pricing on Friday and Saturday",
]

PROMO_BADGES = [
    {"label": "Access to mineral water", "color": "blue"},
    {"label": "Diet meals", "color": "green"},
    {"label": "Doctor consultation", "color": "teal"},
]

SURROUNDINGS = [
    {"name": "Chortoq mineral area", "distance": "nearby", "type": "wellness"},
    {"name": "Namangan city", "distance": "approx. 25 km", "type": "city"},
    {"name": "Local bazaar", "distance": "approx. 3 km", "type": "shopping"},
]

VENUES = [
    {"name": "Medical department", "type": "medical", "capacity": 60},
    {"name": "Dining hall", "type": "dining", "capacity": 180},
    {"name": "Walking garden", "type": "leisure", "capacity": 120},
    {"name": "Mineral bath area", "type": "treatment", "capacity": 30},
]

MEAL_SCHEDULE = [
    {"name": "Breakfast", "time": "08:00-09:30", "board": "all"},
    {"name": "Lunch", "time": "13:00-14:30", "board": "full_board"},
    {"name": "Dinner", "time": "18:30-20:00", "board": "all"},
]

SERVICE_MATRIX = {
    "included": [
        "accommodation",
        "doctor check for treatment packages",
        "diet meals according to selected board",
        "mineral-water drinking cure",
    ],
    "paid": ["massage upgrade", "private transfer", "extra bed"],
    "on_request": ["special diet", "late checkout", "airport transfer"],
}

MEDICAL_BASE = {
    "departments": ["therapy", "physiotherapy", "hydrotherapy"],
    "diagnostics": [
        "doctor examination",
        "blood pressure monitoring",
        "ECG by request",
    ],
    "procedures": [
        "mineral bath",
        "therapeutic shower",
        "massage",
        "electrotherapy",
        "paraffin therapy",
    ],
}

REVIEW_DATA = [
    {
        "source": ReviewSource.UZWELLNESS,
        "external_id": "chortoq-review-1",
        "reviewer_name": "Madina Karimova",
        "reviewer_country": "Uzbekistan",
        "traveler_type": "family",
        "language": "uz",
        "stayed_at": date(2026, 4, 12),
        "room": "Standard Double Room",
        "rating": 9,
        "score_label": "Excellent",
        "cleanliness": 9,
        "amenities": 8,
        "location": 9,
        "service": 9,
        "treatment": 9,
        "value": 8,
        "food": 8,
        "body": "Sokin joy, mineral suv va shifokor nazorati yaxshi tashkil qilingan.",
        "translated_body": "Quiet place with well-organized mineral water treatment.",
        "positive_tags": ["quiet location", "mineral water", "doctor care"],
        "negative_tags": [],
        "reply_body": "Thank you for your feedback. We are glad you enjoyed the stay.",
    },
    {
        "source": ReviewSource.GOOGLE,
        "external_id": "chortoq-review-2",
        "reviewer_name": "Aziz Rahmonov",
        "reviewer_country": "Uzbekistan",
        "traveler_type": "couple",
        "language": "ru",
        "stayed_at": date(2026, 3, 20),
        "room": "Superior Twin Room",
        "rating": 8,
        "score_label": "Very good",
        "cleanliness": 8,
        "amenities": 8,
        "location": 9,
        "service": 8,
        "treatment": 9,
        "value": 8,
        "food": 8,
        "body": "Хорошая лечебная база, процедуры назначали после осмотра врача.",
        "translated_body": "Good treatment base; procedures were assigned after doctor exam.",
        "positive_tags": ["treatment base", "procedures"],
        "negative_tags": [],
    },
    {
        "source": ReviewSource.UZWELLNESS,
        "external_id": "chortoq-review-3",
        "reviewer_name": "Guest User",
        "reviewer_country": "Kazakhstan",
        "traveler_type": "solo",
        "language": "en",
        "stayed_at": date(2026, 2, 8),
        "room": "Standard Single Room",
        "rating": 8,
        "score_label": "Very good",
        "cleanliness": 8,
        "amenities": 7,
        "location": 8,
        "service": 8,
        "treatment": 9,
        "value": 8,
        "food": 7,
        "body": "Simple room, good mineral-water program, and calm environment.",
        "positive_tags": ["calm environment", "mineral program"],
        "negative_tags": ["simple room"],
    },
    {
        "source": ReviewSource.UZWELLNESS,
        "external_id": "chortoq-review-4",
        "reviewer_name": "Nilufar",
        "reviewer_country": "Uzbekistan",
        "traveler_type": "family",
        "language": "uz",
        "stayed_at": date(2026, 1, 14),
        "room": "Family Suite",
        "rating": 9,
        "score_label": "Excellent",
        "cleanliness": 9,
        "amenities": 9,
        "location": 9,
        "service": 9,
        "treatment": 8,
        "value": 9,
        "food": 9,
        "body": "Oilaviy xona keng, ovqatlanish tartibli, bolalar bilan kelishga qulay.",
        "translated_body": "Family room is spacious; meals are organized well.",
        "positive_tags": ["family room", "food", "clean"],
        "negative_tags": [],
    },
    {
        "source": ReviewSource.UZWELLNESS,
        "external_id": "chortoq-review-5",
        "reviewer_name": "Sergey",
        "reviewer_country": "Russia",
        "traveler_type": "solo",
        "language": "ru",
        "stayed_at": date(2025, 12, 2),
        "room": "Standard Double Room",
        "rating": 8,
        "score_label": "Very good",
        "cleanliness": 9,
        "amenities": 8,
        "location": 8,
        "service": 8,
        "treatment": 8,
        "value": 8,
        "food": 8,
        "body": "Минеральная вода и прогулочная зона понравились, персонал внимательный.",
        "translated_body": "Liked the mineral water and walking area; staff was attentive.",
        "positive_tags": ["staff", "walking area"],
        "negative_tags": [],
    },
    {
        "source": ReviewSource.UZWELLNESS,
        "external_id": "chortoq-review-6",
        "reviewer_name": "Guest User",
        "reviewer_country": "Uzbekistan",
        "traveler_type": "business",
        "language": "en",
        "stayed_at": date(2025, 11, 18),
        "room": "Superior Twin Room",
        "rating": 9,
        "score_label": "Excellent",
        "cleanliness": 9,
        "amenities": 8,
        "location": 9,
        "service": 9,
        "treatment": 9,
        "value": 8,
        "food": 8,
        "body": "Good value for a short recovery stay with treatment included.",
        "positive_tags": ["value", "treatment included"],
        "negative_tags": [],
    },
]


if __name__ == "__main__":
    asyncio.run(main())
