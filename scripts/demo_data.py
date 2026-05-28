"""Reset and populate the database with a full-featured demo dataset.

Usage:
    uv run python -m scripts.demo_data

This script is intentionally destructive for demo environments: it clears
application data and recreates a coherent dataset that exercises the main API
surfaces.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from html import escape
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.pricing import calculate_night_price
from app.core.security import hash_password
from app.models import (
    Amenity,
    AmenityCost,
    BoardType,
    Booking,
    BookingExtraBed,
    BookingStatus,
    BookingType,
    ConfirmationType,
    Destination,
    ExchangeRate,
    ExtraBedConfig,
    Notification,
    Package,
    PackageItem,
    PackageItemType,
    Payment,
    PaymentMethod,
    PaymentStatus,
    PaymentTiming,
    PropertyType,
    RatePlan,
    RefreshToken,
    Region,
    Room,
    RoomAvailability,
    RoomImage,
    RoomPricePeriod,
    RoomView,
    Sanatorium,
    SanatoriumAmenity,
    SanatoriumImage,
    SanatoriumReview,
    SanatoriumStatus,
    TransferDirection,
    TransferRequest,
    TransferStatus,
    TreatmentProgram,
    User,
    UserRole,
    VehicleType,
    VisaPurpose,
    VisaRequest,
    VisaStatus,
    WellnessCategory,
)

SUPER_ADMIN_EMAIL = "admin@uzwellness.com"
DEFAULT_PASSWORD = "12345678"
CUSTOMER_PASSWORD = "12345678"
AGENT_PASSWORD = "12345678"
USD_UZS = Decimal("12800.000000")


def tr(uz: str, ru: str, en: str) -> dict[str, str]:
    return {"uz": uz, "ru": ru, "en": en}


def money(value: str) -> Decimal:
    return Decimal(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def demo_media_file(url: str, title: str) -> None:
    prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
    if not url.startswith(prefix):
        return
    relative = url[len(prefix) :]
    path = Path(settings.UPLOAD_DIR) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_title = escape(title)
    path.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
                '<rect width="1200" height="800" fill="#f4f7f4"/>',
                '<rect x="60" y="60" width="1080" height="680" rx="28" fill="#dbe8df"/>',
                '<path d="M0 610 C260 500 380 690 620 560 C840 440 980 620 1200 500 L1200 800 L0 800 Z" fill="#92ad9a"/>',
                '<circle cx="970" cy="190" r="86" fill="#f0c96a"/>',
                f'<text x="600" y="382" text-anchor="middle" font-family="Arial, sans-serif" font-size="56" font-weight="700" fill="#23423a">{safe_title}</text>',
                '<text x="600" y="452" text-anchor="middle" font-family="Arial, sans-serif" font-size="30" fill="#47645b">UzWellness demo media</text>',
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )


REGIONS = [
    ("toshkent", tr("Toshkent viloyati", "Ташкентская область", "Tashkent Region")),
    ("samarqand", tr("Samarqand", "Самаркандская область", "Samarkand Region")),
    ("buxoro", tr("Buxoro", "Бухарская область", "Bukhara Region")),
    ("jizzax", tr("Jizzax", "Джизакская область", "Jizzakh Region")),
    ("namangan", tr("Namangan", "Наманганская область", "Namangan Region")),
    ("fargona", tr("Farg'ona", "Ферганская область", "Fergana Region")),
]

DESTINATIONS = [
    {
        "slug": "chimgan-mountains",
        "name": tr("Chimgan tog'lari", "Чимганские горы", "Chimgan Mountains"),
        "tagline": tr(
            "Tog' havosi, mineral suv va sokin dam olish",
            "Горный воздух, минеральная вода и спокойный отдых",
            "Mountain air, mineral water, and quiet recovery",
        ),
        "description": tr(
            "Toshkentdan qisqa masofadagi sanatoriya va kurortlar.",
            "Санатории и курорты недалеко от Ташкента.",
            "Sanatoriums and resorts a short drive from Tashkent.",
        ),
        "hero_image_url": "/uploads/demo/destinations/chimgan.svg",
        "lat": money("41.550000"),
        "lng": money("70.016700"),
    },
    {
        "slug": "samarkand",
        "name": tr("Samarqand", "Самарканд", "Samarkand"),
        "tagline": tr(
            "Tarixiy shahar ichida premium tiklanish",
            "Премиальное восстановление в историческом городе",
            "Premium recovery inside a heritage city",
        ),
        "description": tr(
            "Shahar sayohati va wellness dasturlari birlashtirilgan yo'nalish.",
            "Направление, сочетающее экскурсии и wellness-программы.",
            "A destination combining city touring with wellness programs.",
        ),
        "hero_image_url": "/uploads/demo/destinations/samarkand.svg",
        "lat": money("39.654200"),
        "lng": money("66.959700"),
    },
    {
        "slug": "zaamin-national-park",
        "name": tr("Zomin milliy bog'i", "Зааминский нацпарк", "Zaamin National Park"),
        "tagline": tr(
            "Qarag'ay o'rmonlari va baland tog' terapiyasi",
            "Сосновые леса и высотная терапия",
            "Pine forests and altitude therapy",
        ),
        "description": tr(
            "Jizzax tog'larida nafas olish va reabilitatsiya dasturlari.",
            "Респираторные и реабилитационные программы в горах Джизака.",
            "Respiratory and rehabilitation programs in the Jizzakh mountains.",
        ),
        "hero_image_url": "/uploads/demo/destinations/zaamin.svg",
        "lat": money("39.950000"),
        "lng": money("68.400000"),
    },
    {
        "slug": "fergana-valley",
        "name": tr("Farg'ona vodiysi", "Ферганская долина", "Fergana Valley"),
        "tagline": tr(
            "Mineral buloqlar va an'anaviy mehmondo'stlik",
            "Минеральные источники и традиционное гостеприимство",
            "Mineral springs and traditional hospitality",
        ),
        "description": tr(
            "Vodiydagi sanatoriyalar, spa va oilaviy dam olish maskanlari.",
            "Санатории, спа и семейные курорты долины.",
            "Valley sanatoriums, spas, and family resorts.",
        ),
        "hero_image_url": "/uploads/demo/destinations/fergana.svg",
        "lat": money("40.389200"),
        "lng": money("71.783300"),
    },
]

USERS = [
    {
        "email": SUPER_ADMIN_EMAIL,
        "password": DEFAULT_PASSWORD,
        "role": UserRole.SUPER_ADMIN,
        "full_name": "UzWellness Super Admin",
        "phone": "+998900000001",
    },
    {
        "email": "zaamin@uzwellness.com",
        "password": DEFAULT_PASSWORD,
        "role": UserRole.ADMIN,
        "full_name": "Zomin Shifo Admin",
        "phone": "+998900000101",
    },
    {
        "email": "chortoq@uzwellness.com",
        "password": DEFAULT_PASSWORD,
        "role": UserRole.ADMIN,
        "full_name": "Chortoq Mineral Admin",
        "phone": "+998900000102",
    },
    {
        "email": "chinobod@uzwellness.com",
        "password": DEFAULT_PASSWORD,
        "role": UserRole.ADMIN,
        "full_name": "Chinobod Admin",
        "phone": "+998900000103",
    },
    {
        "email": "samarkand@uzwellness.com",
        "password": DEFAULT_PASSWORD,
        "role": UserRole.ADMIN,
        "full_name": "Samarkand Wellness Admin",
        "phone": "+998900000104",
    },
    {
        "email": "humson@uzwellness.com",
        "password": DEFAULT_PASSWORD,
        "role": UserRole.ADMIN,
        "full_name": "Humson Buloq Admin",
        "phone": "+998900000105",
    },
    {
        "email": "agent@uzwellness.com",
        "password": AGENT_PASSWORD,
        "role": UserRole.AGENT,
        "full_name": "Silk Road Travel Agent",
        "phone": "+998901112233",
    },
    {
        "email": "ali@gmail.com",
        "password": CUSTOMER_PASSWORD,
        "role": UserRole.CUSTOMER,
        "full_name": "Ali Karimov",
        "phone": "+998901234567",
    },
    {
        "email": "zulfiya@gmail.com",
        "password": CUSTOMER_PASSWORD,
        "role": UserRole.CUSTOMER,
        "full_name": "Zulfiya Yusupova",
        "phone": "+998907654321",
    },
    {
        "email": "malika@gmail.com",
        "password": CUSTOMER_PASSWORD,
        "role": UserRole.CUSTOMER,
        "full_name": "Malika Rahimova",
        "phone": "+998946667788",
    },
]

AMENITIES = [
    ("wifi", "connectivity", "wifi", tr("Wi-Fi", "Wi-Fi", "Wi-Fi")),
    ("pool", "wellness", "waves", tr("Basseyn", "Бассейн", "Pool")),
    ("spa", "wellness", "sparkles", tr("Spa markazi", "Спа-центр", "Spa center")),
    (
        "doctor",
        "medical",
        "stethoscope",
        tr("Shifokor nazorati", "Наблюдение врача", "Doctor supervision"),
    ),
    (
        "mineral-water",
        "medical",
        "droplets",
        tr("Mineral suv", "Минеральная вода", "Mineral water"),
    ),
    (
        "physio",
        "medical",
        "activity",
        tr("Fizioterapiya", "Физиотерапия", "Physiotherapy"),
    ),
    ("gym", "sport", "dumbbell", tr("Sport zal", "Тренажерный зал", "Gym")),
    (
        "parking",
        "transport",
        "parking-circle",
        tr("Avtoturargoh", "Парковка", "Parking"),
    ),
    (
        "airport-transfer",
        "transport",
        "plane",
        tr("Aeroport transferi", "Трансфер из аэропорта", "Airport transfer"),
    ),
    ("restaurant", "food", "utensils", tr("Restoran", "Ресторан", "Restaurant")),
    ("kids-club", "family", "baby", tr("Bolalar klubi", "Детский клуб", "Kids club")),
    (
        "conference",
        "business",
        "briefcase",
        tr("Konferensiya zali", "Конференц-зал", "Conference hall"),
    ),
    (
        "yoga",
        "wellness",
        "person-standing",
        tr("Yoga studiyasi", "Йога-студия", "Yoga studio"),
    ),
    ("sauna", "wellness", "flame", tr("Sauna", "Сауна", "Sauna")),
    ("fitobar", "food", "leaf", tr("Fito bar", "Фито бар", "Phyto bar")),
    ("lab", "medical", "microscope", tr("Laboratoriya", "Лаборатория", "Laboratory")),
]

HUMSON_STAY_COLUMNS = [
    {
        "code": "1_4",
        "label": tr("1-4 sutka", "1-4 суток", "1-4 nights"),
        "min_days": 1,
        "max_days": 4,
    },
    {
        "code": "5",
        "label": tr("5 sutka", "5 суток", "5 nights"),
        "min_days": 5,
        "max_days": 5,
    },
    {
        "code": "7",
        "label": tr("7 sutka", "7 суток", "7 nights"),
        "min_days": 7,
        "max_days": 7,
    },
    {
        "code": "10",
        "label": tr("10 sutka", "10 суток", "10 nights"),
        "min_days": 10,
        "max_days": 10,
    },
]


def _all_stays() -> dict[str, bool]:
    return {"1_4": True, "5": True, "7": True, "10": True}


def _from_5_days() -> dict[str, bool]:
    return {"1_4": False, "5": True, "7": True, "10": True}


def _from_7_days() -> dict[str, bool]:
    return {"1_4": False, "5": False, "7": True, "10": True}


def _only_10_days() -> dict[str, bool]:
    return {"1_4": False, "5": False, "7": False, "10": True}


def humson_inclusion(
    code: str, title: dict[str, str], category: str, included_for: dict[str, bool]
) -> dict:
    return {
        "code": code,
        "title": title,
        "category": category,
        "included_for": included_for,
    }


HUMSON_PROGRAM_INCLUSIONS = [
    humson_inclusion(
        "meals_4x",
        tr("4 mahal ovqat", "4-х разовое питание", "4 meals a day"),
        "food",
        _all_stays(),
    ),
    humson_inclusion(
        "phyto_bar", tr("Fito bar", "Фито бар", "Phyto bar"), "food", _all_stays()
    ),
    humson_inclusion(
        "indoor_outdoor_pool",
        tr(
            "Yopiq va ochiq basseyn",
            "Крытый и открытый бассейн",
            "Indoor and outdoor pool",
        ),
        "wellness",
        _all_stays(),
    ),
    humson_inclusion(
        "playstation_room",
        tr("PlayStation xonasi", "Комната для игры Play Station", "PlayStation room"),
        "leisure",
        _all_stays(),
    ),
    humson_inclusion(
        "bicycles",
        tr("Hududdagi velosipedlar", "Велосипеды на территории", "Bicycles on site"),
        "leisure",
        _all_stays(),
    ),
    humson_inclusion(
        "hippotherapy",
        tr("Ippoterapiya", "Иппотерапия", "Hippotherapy"),
        "wellness",
        _all_stays(),
    ),
    humson_inclusion(
        "women_hairdresser",
        tr(
            "Ayollar sartaroshxonasi",
            "Парикмахерская для женщин",
            "Women's hairdresser",
        ),
        "service",
        _all_stays(),
    ),
    humson_inclusion(
        "kids_animators",
        tr("Bolalar animatorlari", "Аниматоры для детей", "Kids animators"),
        "children",
        _all_stays(),
    ),
    humson_inclusion(
        "nanny_service",
        tr(
            "3 yoshdan bolalar uchun enaga xizmati",
            "Услуги няни для детей от 3-х лет",
            "Nanny service for children from 3 years",
        ),
        "children",
        _all_stays(),
    ),
    humson_inclusion(
        "gym", tr("Trenajyor zal", "Тренажёрный зал", "Gym"), "sport", _all_stays()
    ),
    humson_inclusion(
        "billiards_tennis",
        tr(
            "Bilyard va stol tennisi",
            "Бильярд, настольный теннис",
            "Billiards and table tennis",
        ),
        "sport",
        _all_stays(),
    ),
    humson_inclusion(
        "sports_fields",
        tr(
            "Futbol, basketbol, voleybol va tennis korti",
            "Футбольное, баскетбольное, волейбольное поля и теннисный корт",
            "Football, basketball, volleyball fields and tennis court",
        ),
        "sport",
        _all_stays(),
    ),
    humson_inclusion(
        "cinema", tr("Kinozal", "Кинотеатр", "Cinema"), "leisure", _all_stays()
    ),
    humson_inclusion(
        "doctor_observation",
        tr(
            "Shifokor ko'rigi va nazorati",
            "Осмотр и наблюдение врачей",
            "Doctor check and observation",
        ),
        "medical",
        _from_5_days(),
    ),
    humson_inclusion(
        "lab_tests",
        tr("Laborator analizlar", "Лабораторные анализы", "Laboratory tests"),
        "medical",
        _from_5_days(),
    ),
    humson_inclusion(
        "therapeutic_massage",
        tr(
            "Mahalliy davolovchi massaj",
            "Лечебный массаж локально",
            "Local therapeutic massage",
        ),
        "medical",
        _all_stays(),
    ),
    humson_inclusion(
        "physiotherapy",
        tr(
            "Fizioterapevtik muolajalar",
            "Физиотерапевтические процедуры",
            "Physiotherapy procedures",
        ),
        "medical",
        _from_5_days(),
    ),
    humson_inclusion(
        "hydrotherapy",
        tr(
            "Gidroterapevtik muolajalar",
            "Гидротерапевтические процедуры",
            "Hydrotherapy procedures",
        ),
        "medical",
        _from_5_days(),
    ),
    humson_inclusion(
        "ozonotherapy",
        tr("Ozonoterapiya", "Озонотерапия", "Ozonotherapy"),
        "medical",
        _from_7_days(),
    ),
    humson_inclusion(
        "sauna_once",
        tr(
            "Yashash davomida 1 marta sauna",
            "Сауна 1 раз за проживание",
            "Sauna once per stay",
        ),
        "wellness",
        _only_10_days(),
    ),
]


def humson_procedure(
    code: str, title: dict[str, str], category: str
) -> tuple[str, dict]:
    return (
        category,
        {
            "code": code,
            "image_url": f"/uploads/demo/procedures/humson/{code}.svg",
            "description": title,
        },
    )


HUMSON_PROCEDURES = [
    humson_procedure(
        "circular_shower",
        tr("Sirkulyar dush", "Циркулярный душ", "Circular shower"),
        "hydrotherapy",
    ),
    humson_procedure(
        "sharko_shower",
        tr("Sharko dushi", "Душ Шарко", "Charcot shower"),
        "hydrotherapy",
    ),
    humson_procedure(
        "cascade_shower",
        tr("Kaskadli dush", "Каскадный душ", "Cascade shower"),
        "hydrotherapy",
    ),
    humson_procedure(
        "colon_hydrotherapy",
        tr("Gidrokolonoterapiya", "Гидроколонотерапия", "Colon hydrotherapy"),
        "hydrotherapy",
    ),
    humson_procedure(
        "medical_hydromassage_bath",
        tr(
            "Tibbiy gidromassaj vannasi",
            "Медицинская гидромассажная ванна",
            "Medical hydromassage bath",
        ),
        "hydrotherapy",
    ),
    humson_procedure(
        "vichy_shower", tr("Vishi dushi", "Душ Виши", "Vichy shower"), "hydrotherapy"
    ),
    humson_procedure(
        "ascending_shower",
        tr("Ko'tariluvchi dush", "Восходящий душ", "Ascending shower"),
        "hydrotherapy",
    ),
    humson_procedure(
        "pearl_baths",
        tr("Marvarid vannalari", "Жемчужные ванны", "Pearl baths"),
        "hydrotherapy",
    ),
    humson_procedure(
        "hand_baths", tr("Qo'l vannalari", "Ручные ванны", "Hand baths"), "hydrotherapy"
    ),
    humson_procedure(
        "foot_baths", tr("Oyoq vannalari", "Ножные ванны", "Foot baths"), "hydrotherapy"
    ),
    humson_procedure("ecg", tr("EKG", "ЭКГ", "ECG"), "physiotherapy"),
    humson_procedure(
        "electrocardiograph",
        tr("Elektrokardiograf", "Электрокардиограф", "Electrocardiograph"),
        "physiotherapy",
    ),
    humson_procedure(
        "uhf_ultratherm",
        tr("UVCh-ultraterm", "УВЧ-Ультратерм", "UHF Ultratherm"),
        "physiotherapy",
    ),
    humson_procedure(
        "radiotherm", tr("Radioterm", "Радиотерм", "Radiotherm"), "physiotherapy"
    ),
    humson_procedure(
        "interference_therapy",
        tr("Interferens terapiya", "Интерференцтерапия", "Interference therapy"),
        "physiotherapy",
    ),
    humson_procedure(
        "stereodinator",
        tr("Stereodinator", "Стереодинатор", "Stereodinator"),
        "physiotherapy",
    ),
    humson_procedure(
        "neuroton", tr("Neyroton", "Нейротон", "Neuroton"), "physiotherapy"
    ),
    humson_procedure(
        "massage_couch",
        tr("Massaj kushetkasi", "Массажная кушетка", "Massage couch"),
        "physiotherapy",
    ),
    humson_procedure(
        "laser_therapy",
        tr("Lazeroterapiya", "Лазеротерапия", "Laser therapy"),
        "physiotherapy",
    ),
    humson_procedure(
        "darsonvalization",
        tr("Darsonvalizatsiya", "Дарсонвализация", "Darsonvalization"),
        "physiotherapy",
    ),
    humson_procedure("hi_top", tr("Hi-Top", "Hi-Top", "Hi-Top"), "physiotherapy"),
    humson_procedure(
        "mechanomassage",
        tr("Mexanomassaj", "Механомассаж", "Mechanomassage"),
        "physiotherapy",
    ),
    humson_procedure(
        "ufo_tubus", tr("UFO tubus", "УФО (тубус)", "UFO tubus"), "physiotherapy"
    ),
    humson_procedure(
        "inhalation", tr("Ingalyatsiya", "Ингаляция", "Inhalation"), "physiotherapy"
    ),
    humson_procedure(
        "magnetotherapy",
        tr("Magnitoterapiya", "Магнитотерапия", "Magnetotherapy"),
        "physiotherapy",
    ),
    humson_procedure(
        "infrared", tr("Infraruj", "Инфраруж", "Infrared therapy"), "physiotherapy"
    ),
    humson_procedure(
        "phonophoresis", tr("Fonoforez", "Фонофорез", "Phonophoresis"), "physiotherapy"
    ),
    humson_procedure("massage", tr("Massaj", "Массаж", "Massage"), "physiotherapy"),
    humson_procedure(
        "ozonotherapy",
        tr("Ozonoterapiya", "Озонотерапия", "Ozonotherapy"),
        "physiotherapy",
    ),
    humson_procedure(
        "lymphatic_drainage",
        tr("Limfodrenaj", "Лимфодренаж", "Lymphatic drainage"),
        "physiotherapy",
    ),
]


def humson_medical_base() -> dict:
    procedures: dict[str, list[dict]] = {}
    for category, item in HUMSON_PROCEDURES:
        procedures.setdefault(category, []).append(item)
    return {
        "description": tr(
            "Humson Buloq davolash dasturi shifokor tavsiyasiga ko'ra gidroterapiya, fizioterapiya va wellness xizmatlarini birlashtiradi.",
            "Лечебная программа Humson Buloq объединяет гидротерапию, физиотерапию и wellness-услуги строго по назначению врача.",
            "Humson Buloq combines hydrotherapy, physiotherapy, and wellness services strictly by doctor's prescription.",
        ),
        "procedures_per_week": 14,
        "min_age_for_treatment": 4,
        "checkups_included": 2,
        "natural_resources": ["mountain_air", "spring_water", "forest_zone"],
        "procedures": procedures,
        "stay_inclusions": [
            {
                "min_days": 1,
                "inclusions": ["meals_4x", "pool_access", "leisure_services"],
            },
            {
                "min_days": 5,
                "inclusions": [
                    "doctor_observation",
                    "lab_tests",
                    "physiotherapy",
                    "hydrotherapy",
                ],
            },
            {"min_days": 7, "inclusions": ["ozonotherapy"]},
            {"min_days": 10, "inclusions": ["sauna_once"]},
        ],
        "stay_duration_columns": HUMSON_STAY_COLUMNS,
        "stay_program_inclusions": HUMSON_PROGRAM_INCLUSIONS,
    }


def humson_service_item(
    code: str, title: dict[str, str], icon: str, category: str
) -> dict:
    return {
        "code": code,
        "title": title,
        "description": tr(
            f"{title['uz']} xizmatidan foydalanish mumkin.",
            f"Доступна услуга: {title['ru']}.",
            f"{title['en']} is available.",
        ),
        "is_available": True,
        "cost": AmenityCost.FREE.value,
        "hours": None,
        "location": None,
        "icon": icon,
        "tags": [category],
    }


HUMSON_SERVICE_MATRIX = {
    "food_drink": {
        "title": tr("Ovqatlanish", "Питание", "Food and drink"),
        "items": [
            humson_service_item(
                "meals_4x",
                tr("4 mahal ovqat", "4-х разовое питание", "4 meals a day"),
                "utensils",
                "food",
            ),
            humson_service_item(
                "phyto_bar", tr("Fito bar", "Фито бар", "Phyto bar"), "leaf", "food"
            ),
        ],
    },
    "wellness": {
        "title": tr(
            "Wellness va dam olish", "Wellness и отдых", "Wellness and leisure"
        ),
        "items": [
            humson_service_item(
                "pool",
                tr(
                    "Yopiq va ochiq basseyn",
                    "Крытый и открытый бассейн",
                    "Indoor and outdoor pool",
                ),
                "waves",
                "wellness",
            ),
            humson_service_item(
                "sauna", tr("Sauna", "Сауна", "Sauna"), "flame", "wellness"
            ),
            humson_service_item(
                "hippotherapy",
                tr("Ippoterapiya", "Иппотерапия", "Hippotherapy"),
                "activity",
                "wellness",
            ),
        ],
    },
    "medical_department": {
        "title": tr("Tibbiy bo'lim", "Медицинское отделение", "Medical department"),
        "items": [
            humson_service_item(
                "doctor_observation",
                tr("Shifokor ko'rigi", "Осмотр врачей", "Doctor check"),
                "stethoscope",
                "medical",
            ),
            humson_service_item(
                "lab_tests",
                tr("Laborator analizlar", "Лабораторные анализы", "Laboratory tests"),
                "microscope",
                "medical",
            ),
            humson_service_item(
                "physiotherapy",
                tr("Fizioterapiya", "Физиотерапия", "Physiotherapy"),
                "activity",
                "medical",
            ),
            humson_service_item(
                "hydrotherapy",
                tr("Gidroterapiya", "Гидротерапия", "Hydrotherapy"),
                "droplets",
                "medical",
            ),
            humson_service_item(
                "ozonotherapy",
                tr("Ozonoterapiya", "Озонотерапия", "Ozonotherapy"),
                "sparkles",
                "medical",
            ),
        ],
    },
    "front_desk": {"title": tr("Qabulxona", "Ресепшен", "Front desk"), "items": []},
    "cleaning": {"title": tr("Tozalik", "Уборка", "Cleaning"), "items": []},
    "business": {"title": tr("Biznes", "Бизнес", "Business"), "items": []},
    "parking": {
        "title": tr("Avtoturargoh", "Парковка", "Parking"),
        "items": [
            humson_service_item(
                "parking",
                tr("Avtoturargoh", "Парковка", "Parking"),
                "parking-circle",
                "parking",
            )
        ],
    },
    "internet": {
        "title": tr("Internet", "Интернет", "Internet"),
        "items": [
            humson_service_item(
                "wifi", tr("Wi-Fi", "Wi-Fi", "Wi-Fi"), "wifi", "internet"
            )
        ],
    },
    "children": {
        "title": tr("Bolalar", "Дети", "Children"),
        "items": [
            humson_service_item(
                "kids_animators",
                tr("Bolalar animatorlari", "Аниматоры для детей", "Kids animators"),
                "baby",
                "children",
            ),
            humson_service_item(
                "nanny_service",
                tr("Enaga xizmati", "Услуги няни", "Nanny service"),
                "baby",
                "children",
            ),
            humson_service_item(
                "playstation_room",
                tr("PlayStation xonasi", "Комната Play Station", "PlayStation room"),
                "gamepad-2",
                "children",
            ),
        ],
    },
    "accessibility": {
        "title": tr("Qulay kirish", "Доступность", "Accessibility"),
        "items": [],
    },
    "languages": ["uz", "ru"],
    "notes": tr(
        "Tibbiy muolajalar shifokor tavsiyasi bilan, xizmatlar esa yashash muddatiga qarab taqdim etiladi.",
        "Медицинские процедуры предоставляются по назначению врача, услуги зависят от срока проживания.",
        "Medical procedures are provided by doctor's prescription, and inclusions depend on stay duration.",
    ),
}


HUMSON_POLICIES = {
    "check_in": {
        "instructions": tr(
            "Zaezd 12:30 dan, vyezd 10:30 gacha. Pasport va bron tasdig'ini ko'rsating.",
            "Заезд с 12:30, выезд до 10:30. Предъявите паспорт и подтверждение брони.",
            "Check-in is from 12:30, check-out is until 10:30. Show passport and booking confirmation.",
        ),
        "required_documents": ["passport", "booking_confirmation", "medical_summary"],
    },
    "children": {"allowed": True, "min_age": 0, "treatment_min_age": 4},
    "extra_bed": {
        "available": True,
        "crib_available": False,
        "price": "500000.00",
        "currency": "UZS",
        "age_price_bands": [
            {
                "min_age": 4,
                "max_age": 10,
                "price_per_night": "500000.00",
                "currency": "UZS",
                "includes": ["meals", "extra_mattress", "bedding"],
            },
            {
                "min_age": 11,
                "price_per_night": "1000000.00",
                "currency": "UZS",
                "includes": ["meals", "extra_mattress", "bedding"],
            },
        ],
    },
    "breakfast": {"included": True, "style": "4_meals", "hours": "08:00-20:00"},
    "pets": {"allowed": False, "service_animals_allowed": True},
    "cancellation": {
        "free_cancellation_until_days_before": 5,
        "penalty_percent": "50.00",
    },
    "payment": {
        "methods": [
            "cash",
            "bank_transfer",
            "uzcard",
            "visa",
            "mastercard",
            "jcb",
            "unionpay",
            "mir",
        ],
        "deposit_required": True,
        "deposit_percent": "20.00",
    },
    "fees": {
        "mandatory_fees": [],
        "optional_fees": ["additional_accommodation", "extra_procedures"],
    },
}


SANATORIUMS = [
    {
        "slug": "zomin-shifo-resort",
        "admin": "zaamin@uzwellness.com",
        "region": "jizzax",
        "destination": "zaamin-national-park",
        "name": tr("Zomin Shifo Resort", "Заамин Шифо Resort", "Zaamin Shifo Resort"),
        "description": tr(
            "Qarag'ay o'rmonlari orasidagi baland tog' sanatoriysi: nafas yo'llari, reabilitatsiya va sokin oilaviy dam olish uchun.",
            "Высокогорный санаторий среди сосновых лесов: дыхательные программы, реабилитация и спокойный семейный отдых.",
            "A high-altitude sanatorium among pine forests for respiratory care, rehabilitation, and quiet family stays.",
        ),
        "city": "Zomin",
        "address": tr(
            "Jizzax viloyati, Zomin tumani, Milliy bog' hududi",
            "Джизакская область, Зааминский район, территория нацпарка",
            "Jizzakh Region, Zaamin District, National Park area",
        ),
        "lat": money("39.960100"),
        "lng": money("68.395900"),
        "stars": 5,
        "phones": ["+998724505050", "+998901111050"],
        "website": "https://zomin-shifo.uzwellness.com",
        "check_in_time": time(14, 0),
        "check_out_time": time(12, 0),
        "pets_allowed": False,
        "service_animals_allowed": True,
        "min_checkin_age": 18,
        "quiet_hours_from": time(22, 30),
        "quiet_hours_to": time(7, 0),
        "payment_methods": ["cash", "bank_transfer", "uzcard", "visa", "mastercard"],
        "house_rules": tr(
            "Davolash zonalarida shovqin qilish va chekish mumkin emas.",
            "В лечебных зонах запрещены шум и курение.",
            "Noise and smoking are not allowed in treatment areas.",
        ),
        "cancellation_policy": tr(
            "Kelishdan 5 kun oldin bepul bekor qilish mumkin.",
            "Бесплатная отмена за 5 дней до заезда.",
            "Free cancellation up to 5 days before arrival.",
        ),
        "weekly_schedule": {
            "monday": "08:00-20:00",
            "tuesday": "08:00-20:00",
            "wednesday": "08:00-20:00",
            "thursday": "08:00-20:00",
            "friday": "08:00-20:00",
            "saturday": "09:00-18:00",
            "sunday": "09:00-16:00",
        },
        "property_type": PropertyType.SANATORIUM,
        "wellness_category": None,
        "treatment_focuses": ["respiratory", "neurological", "wellness"],
        "year_opened": 2018,
        "languages_spoken": ["uz", "ru", "en"],
        "highlights": [
            "High-altitude respiratory therapy",
            "Pine forest walking routes",
            "Mineral inhalation rooms",
        ],
        "surroundings": [
            {"name": "Zomin milliy bog'i", "type": "national_park", "distance_m": 600},
            {"name": "Suffa plato", "type": "viewpoint", "distance_m": 8200},
        ],
        "venues": [
            {
                "name": "Archazor Restaurant",
                "type": "restaurant",
                "building": "Main block",
                "hours": "07:30-22:00",
            },
            {
                "name": "Pine Hall",
                "type": "conference",
                "building": "Business wing",
                "hours": "09:00-18:00",
            },
        ],
        "meal_schedule": [
            {
                "meal": "breakfast",
                "time_from": "07:30",
                "time_to": "10:00",
                "style": "buffet",
            },
            {
                "meal": "lunch",
                "time_from": "12:30",
                "time_to": "14:30",
                "style": "diet menu",
            },
            {
                "meal": "dinner",
                "time_from": "18:30",
                "time_to": "20:30",
                "style": "set menu",
            },
        ],
        "platform_commission_percent": money("12.00"),
        "b2b_commission_percent": money("7.00"),
        "agent_discount_tiers": [
            {"min_bookings": 3, "discount_percent": "5"},
            {"min_bookings": 10, "discount_percent": "10"},
        ],
        "amenities": [
            ("wifi", AmenityCost.FREE),
            ("doctor", AmenityCost.FREE),
            ("mineral-water", AmenityCost.FREE),
            ("physio", AmenityCost.PAID),
            ("restaurant", AmenityCost.FREE),
            ("airport-transfer", AmenityCost.ON_REQUEST),
            ("conference", AmenityCost.PAID),
        ],
        "images": [
            ("zomin-hero.svg", True, "Pine forest resort facade"),
            ("zomin-treatment.svg", False, "Respiratory treatment wing"),
            ("zomin-trail.svg", False, "Forest walking trail"),
        ],
    },
    {
        "slug": "chortoq-mineral-spa",
        "admin": "chortoq@uzwellness.com",
        "region": "namangan",
        "destination": "fergana-valley",
        "name": tr("Chortoq Mineral Spa", "Чартак Mineral Spa", "Chortoq Mineral Spa"),
        "description": tr(
            "Mineral buloqlar, balneologiya va oilaviy wellness dasturlariga ixtisoslashgan Namangan sanatoriysi.",
            "Санаторий в Намангане с минеральными источниками, бальнеологией и семейными wellness-программами.",
            "A Namangan sanatorium focused on mineral springs, balneology, and family wellness programs.",
        ),
        "city": "Chortoq",
        "address": tr(
            "Chortoq tumani, Mineral buloqlar ko'chasi 7",
            "Чартакский район, ул. Минеральных источников 7",
            "Chortoq District, 7 Mineral Springs Street",
        ),
        "lat": money("41.066800"),
        "lng": money("71.825600"),
        "stars": 4,
        "phones": ["+998694123333", "+998909009090"],
        "website": "https://chortoq-mineral.uzwellness.com",
        "check_in_time": time(13, 0),
        "check_out_time": time(11, 30),
        "pets_allowed": False,
        "service_animals_allowed": True,
        "min_checkin_age": 16,
        "quiet_hours_from": time(23, 0),
        "quiet_hours_to": time(7, 0),
        "payment_methods": ["cash", "bank_transfer", "uzcard", "visa", "mir"],
        "house_rules": tr(
            "Mineral vanna seanslariga vaqtida kelish talab qilinadi.",
            "На минеральные ванны необходимо приходить вовремя.",
            "Guests must arrive on time for mineral bath sessions.",
        ),
        "cancellation_policy": tr(
            "Kelishdan 3 kun oldin bepul bekor qilish mumkin.",
            "Бесплатная отмена за 3 дня до заезда.",
            "Free cancellation up to 3 days before arrival.",
        ),
        "weekly_schedule": {"daily": "08:00-21:00", "treatment_break": "13:00-14:00"},
        "property_type": PropertyType.SANATORIUM,
        "wellness_category": None,
        "treatment_focuses": [
            "musculoskeletal",
            "dermatology",
            "endocrine",
            "wellness",
        ],
        "year_opened": 2015,
        "languages_spoken": ["uz", "ru"],
        "highlights": ["Mineral baths", "Family wellness plans", "Dietitian menu"],
        "surroundings": [
            {"name": "Chortoq mineral spring", "type": "spring", "distance_m": 250},
            {"name": "Namangan airport", "type": "airport", "distance_m": 32000},
        ],
        "venues": [
            {
                "name": "Buloq Dining",
                "type": "restaurant",
                "building": "Block A",
                "hours": "07:00-21:00",
            },
            {
                "name": "Mineral Bath Center",
                "type": "treatment",
                "building": "Spa block",
                "hours": "08:00-18:00",
            },
        ],
        "meal_schedule": [
            {
                "meal": "breakfast",
                "time_from": "07:00",
                "time_to": "09:30",
                "style": "buffet",
            },
            {
                "meal": "lunch",
                "time_from": "12:00",
                "time_to": "14:00",
                "style": "diet menu",
            },
            {
                "meal": "dinner",
                "time_from": "18:00",
                "time_to": "20:00",
                "style": "buffet",
            },
        ],
        "platform_commission_percent": money("10.00"),
        "b2b_commission_percent": money("6.00"),
        "agent_discount_tiers": [{"min_bookings": 5, "discount_percent": "7"}],
        "amenities": [
            ("wifi", AmenityCost.FREE),
            ("pool", AmenityCost.FREE),
            ("spa", AmenityCost.PAID),
            ("doctor", AmenityCost.FREE),
            ("mineral-water", AmenityCost.FREE),
            ("kids-club", AmenityCost.FREE),
            ("parking", AmenityCost.FREE),
        ],
        "images": [
            ("chortoq-hero.svg", True, "Mineral spa entrance"),
            ("chortoq-pool.svg", False, "Indoor mineral pool"),
            ("chortoq-family.svg", False, "Family garden area"),
        ],
    },
    {
        "slug": "humson-buloq-health-resort",
        "admin": "humson@uzwellness.com",
        "region": "toshkent",
        "destination": "chimgan-mountains",
        "name": tr("Humson Buloq", "Humson Buloq", "Humson Buloq"),
        "description": tr(
            "Toshkent tog'oldi hududidagi sanatorno-kurort kompleks: gidroterapiya, fizioterapiya, basseyn va oilaviy dam olish xizmatlari bilan.",
            "Санаторно-курортный комплекс в предгорьях Ташкента: гидротерапия, физиотерапия, бассейны и семейный отдых.",
            "A sanatorium resort complex in the Tashkent foothills with hydrotherapy, physiotherapy, pools, and family leisure.",
        ),
        "city": "Humson",
        "address": tr(
            "Toshkent viloyati, Bo'stonliq tumani, Humson qishlog'i",
            "Ташкентская область, Бостанлыкский район, поселок Хумсан",
            "Tashkent Region, Bostanliq District, Humson village",
        ),
        "lat": money("41.650400"),
        "lng": money("69.936900"),
        "stars": 4,
        "phones": ["+998991006000", "+998933996000", "+998773606000"],
        "website": "https://www.humsonbuloq.uz",
        "check_in_time": time(12, 30),
        "check_out_time": time(10, 30),
        "pets_allowed": False,
        "service_animals_allowed": True,
        "min_checkin_age": 18,
        "quiet_hours_from": time(22, 30),
        "quiet_hours_to": time(7, 0),
        "payment_methods": [
            "cash",
            "bank_transfer",
            "uzcard",
            "visa",
            "mastercard",
            "jcb",
            "unionpay",
            "mir",
        ],
        "house_rules": tr(
            "Spirtli ichimlik ichish qat'iyan taqiqlangan. Tibbiy muolajalar faqat shifokor tavsiyasi bilan.",
            "Распитие спиртных напитков строго запрещено. Медицинские процедуры строго по назначению врача.",
            "Alcohol consumption is strictly prohibited. Medical procedures are strictly by doctor's prescription.",
        ),
        "cancellation_policy": tr(
            "Kelishdan 5 kun oldin bepul bekor qilish mumkin, keyin 50% jarima qo'llanadi.",
            "Бесплатная отмена за 5 дней до заезда, далее применяется штраф 50%.",
            "Free cancellation up to 5 days before arrival, then a 50% penalty applies.",
        ),
        "weekly_schedule": {
            "reception": "24/7",
            "medical": "08:00-18:00",
            "pool": "08:00-21:00",
            "check_in": "12:30",
            "check_out": "10:30",
            "seasonal_offer": "2025-09-08/2025-12-30",
        },
        "property_type": PropertyType.SANATORIUM,
        "wellness_category": None,
        "treatment_focuses": [
            "respiratory",
            "musculoskeletal",
            "neurological",
            "wellness",
        ],
        "treatment_profile": {
            "main_indications": [
                {
                    "code": "hydrotherapy_recovery",
                    "title": tr("Gidroterapiya", "Гидротерапия", "Hydrotherapy"),
                    "description": tr(
                        "Dushlar, vannalar va gidromassaj muolajalari shifokor tavsiyasi bilan.",
                        "Души, ванны и гидромассажные процедуры по назначению врача.",
                        "Showers, baths, and hydromassage procedures by doctor's prescription.",
                    ),
                },
                {
                    "code": "physiotherapy_recovery",
                    "title": tr("Fizioterapiya", "Физиотерапия", "Physiotherapy"),
                    "description": tr(
                        "EKG, lazeroterapiya, magnitoterapiya va boshqa apparat muolajalari.",
                        "ЭКГ, лазеротерапия, магнитотерапия и другие аппаратные процедуры.",
                        "ECG, laser therapy, magnetotherapy, and other device-based procedures.",
                    ),
                },
            ],
            "additional_indications": [
                {
                    "code": "family_recovery",
                    "title": tr(
                        "Oilaviy tiklanish",
                        "Семейное восстановление",
                        "Family recovery",
                    ),
                    "description": tr(
                        "Bolalar animatorlari, enaga xizmati va sport zonalari bilan oilaviy dam olish.",
                        "Семейный отдых с аниматорами, услугами няни и спортивными зонами.",
                        "Family leisure with animators, nanny service, and sports areas.",
                    ),
                }
            ],
            "contraindications": [
                {
                    "code": "doctor_restriction",
                    "title": tr(
                        "Shifokor cheklovi", "Ограничение врача", "Doctor restriction"
                    ),
                    "description": tr(
                        "Tibbiy muolajalar shifokor ruxsatisiz o'tkazilmaydi.",
                        "Медицинские процедуры не проводятся без назначения врача.",
                        "Medical procedures are not provided without a doctor's prescription.",
                    ),
                }
            ],
            "diagnostics": ["doctor_check", "laboratory_tests", "ecg"],
            "doctor_specialties": ["therapist", "physiotherapist", "hydrotherapist"],
            "notes": tr(
                "Dastur 1-4, 5, 7 va 10 sutkalik yashash muddatiga qarab farqlanadi.",
                "Программа отличается для сроков проживания 1-4, 5, 7 и 10 суток.",
                "The program differs for 1-4, 5, 7, and 10-night stays.",
            ),
        },
        "year_opened": 2019,
        "languages_spoken": ["uz", "ru"],
        "highlights": [
            "20% autumn discount",
            "4 meals a day",
            "Hydrotherapy and physiotherapy",
            "Alcohol-free resort",
        ],
        "promo_badges": [
            {
                "code": "autumn_20_discount",
                "kind": "deal",
                "title": tr("20% chegirma", "20% скидка", "20% discount"),
                "description": tr(
                    "2025-yil 8-sentabrdan 30-dekabrgacha amal qiladi.",
                    "Действует с 8 сентября до 30 декабря 2025 года.",
                    "Valid from September 8 to December 30, 2025.",
                ),
                "icon": "badge-percent",
                "is_active": True,
                "priority": 1,
            },
            {
                "code": "doctor_prescription_only",
                "kind": "trust",
                "title": tr(
                    "Shifokor tavsiyasi bilan",
                    "По назначению врача",
                    "Doctor prescribed",
                ),
                "description": tr(
                    "Barcha tibbiy muolajalar faqat shifokor tavsiyasi bilan o'tkaziladi.",
                    "Все медицинские процедуры строго по назначению врача.",
                    "All medical procedures are strictly by doctor's prescription.",
                ),
                "icon": "stethoscope",
                "is_active": True,
                "priority": 2,
            },
        ],
        "surroundings": [
            {"name": "Humson tog'oldi zonasi", "type": "nature", "distance_m": 300},
            {"name": "Chorvoq suv ombori", "type": "lake", "distance_m": 18000},
        ],
        "venues": [
            {
                "name": "Humson Dining Hall",
                "type": "restaurant",
                "building": "Main block",
                "hours": "08:00-20:00",
            },
            {
                "name": "Hydrotherapy Center",
                "type": "treatment",
                "building": "Medical block",
                "hours": "08:00-18:00",
            },
            {
                "name": "Indoor Pool",
                "type": "pool",
                "building": "Wellness block",
                "hours": "08:00-21:00",
            },
        ],
        "meal_schedule": [
            {
                "meal": "breakfast",
                "time_from": "08:00",
                "time_to": "09:30",
                "style": "set menu",
            },
            {
                "meal": "lunch",
                "time_from": "12:30",
                "time_to": "14:00",
                "style": "set menu",
            },
            {
                "meal": "snack",
                "time_from": "16:30",
                "time_to": "17:00",
                "style": "phyto bar",
            },
            {
                "meal": "dinner",
                "time_from": "18:30",
                "time_to": "20:00",
                "style": "set menu",
            },
        ],
        "service_matrix": HUMSON_SERVICE_MATRIX,
        "medical_base": humson_medical_base(),
        "policies": HUMSON_POLICIES,
        "platform_commission_percent": money("12.00"),
        "b2b_commission_percent": money("7.00"),
        "agent_discount_tiers": [
            {"min_bookings": 3, "discount_percent": "5"},
            {"min_bookings": 10, "discount_percent": "10"},
        ],
        "amenities": [
            ("wifi", AmenityCost.FREE),
            ("pool", AmenityCost.FREE),
            ("doctor", AmenityCost.FREE),
            ("physio", AmenityCost.FREE),
            ("sauna", AmenityCost.FREE),
            ("fitobar", AmenityCost.FREE),
            ("lab", AmenityCost.FREE),
            ("parking", AmenityCost.FREE),
            ("restaurant", AmenityCost.FREE),
        ],
        "images": [
            ("humson-hero.svg", True, "Humson Buloq resort facade"),
            ("humson-hydrotherapy.svg", False, "Hydrotherapy and treatment block"),
            ("humson-pool.svg", False, "Indoor and outdoor pool area"),
        ],
    },
    {
        "slug": "chinobod-health-resort",
        "admin": "chinobod@uzwellness.com",
        "region": "toshkent",
        "destination": "chimgan-mountains",
        "name": tr(
            "Chinobod Health Resort", "Чинобод Health Resort", "Chinobod Health Resort"
        ),
        "description": tr(
            "Toshkent yaqinidagi klinik-diagnostika, spa va biznes qulayliklari bor shahar-tog' kurorti.",
            "Городской горный курорт недалеко от Ташкента с диагностикой, спа и бизнес-инфраструктурой.",
            "A city-mountain resort near Tashkent with diagnostics, spa, and business facilities.",
        ),
        "city": "Toshkent viloyati",
        "address": tr(
            "Qibray tumani, Chinobod yo'li 12",
            "Кибрайский район, Чинободская дорога 12",
            "Qibray District, 12 Chinobod Road",
        ),
        "lat": money("41.383200"),
        "lng": money("69.468100"),
        "stars": 5,
        "phones": ["+998712005050", "+998998887777"],
        "website": "https://chinobod-health.uzwellness.com",
        "check_in_time": time(15, 0),
        "check_out_time": time(12, 0),
        "pets_allowed": True,
        "service_animals_allowed": True,
        "min_checkin_age": 18,
        "quiet_hours_from": time(22, 0),
        "quiet_hours_to": time(7, 0),
        "payment_methods": [
            "cash",
            "bank_transfer",
            "uzcard",
            "visa",
            "mastercard",
            "unionpay",
        ],
        "house_rules": tr(
            "Uy hayvonlari faqat garden wing xonalarida qabul qilinadi.",
            "Питомцы размещаются только в номерах garden wing.",
            "Pets are accepted only in garden wing rooms.",
        ),
        "cancellation_policy": tr(
            "Kelishdan 7 kun oldin bepul, keyin 1 kecha jarima.",
            "Бесплатно за 7 дней, далее штраф за 1 ночь.",
            "Free up to 7 days before arrival, then a 1-night penalty.",
        ),
        "weekly_schedule": {
            "reception": "24/7",
            "clinic": "08:00-19:00",
            "spa": "09:00-22:00",
        },
        "property_type": PropertyType.SANATORIUM,
        "wellness_category": None,
        "treatment_focuses": ["cardiovascular", "digestive", "wellness"],
        "year_opened": 2021,
        "languages_spoken": ["uz", "ru", "en"],
        "highlights": [
            "Full diagnostics",
            "Business-ready rooms",
            "Airport transfer desk",
        ],
        "surroundings": [
            {
                "name": "Tashkent International Airport",
                "type": "airport",
                "distance_m": 28000,
            },
            {"name": "Amirsoy resort road", "type": "landmark", "distance_m": 43000},
        ],
        "venues": [
            {
                "name": "Oqsaroy Restaurant",
                "type": "restaurant",
                "building": "Tower",
                "hours": "07:00-23:00",
            },
            {
                "name": "Executive Hall",
                "type": "conference",
                "building": "Business block",
                "hours": "08:00-20:00",
            },
        ],
        "meal_schedule": [
            {
                "meal": "breakfast",
                "time_from": "07:00",
                "time_to": "10:30",
                "style": "buffet",
            },
            {
                "meal": "lunch",
                "time_from": "12:30",
                "time_to": "15:00",
                "style": "a la carte",
            },
            {
                "meal": "dinner",
                "time_from": "18:30",
                "time_to": "22:00",
                "style": "a la carte",
            },
        ],
        "platform_commission_percent": money("14.00"),
        "b2b_commission_percent": money("8.00"),
        "agent_discount_tiers": [
            {"min_bookings": 2, "discount_percent": "4"},
            {"min_bookings": 8, "discount_percent": "9"},
        ],
        "amenities": [
            ("wifi", AmenityCost.FREE),
            ("pool", AmenityCost.FREE),
            ("spa", AmenityCost.PAID),
            ("gym", AmenityCost.FREE),
            ("restaurant", AmenityCost.FREE),
            ("airport-transfer", AmenityCost.ON_REQUEST),
            ("conference", AmenityCost.PAID),
        ],
        "images": [
            ("chinobod-hero.svg", True, "Main resort building"),
            ("chinobod-suite.svg", False, "Suite view"),
            ("chinobod-spa.svg", False, "Spa treatment area"),
        ],
    },
    {
        "slug": "samarkand-silk-wellness",
        "admin": "samarkand@uzwellness.com",
        "region": "samarqand",
        "destination": "samarkand",
        "name": tr(
            "Samarkand Silk Wellness",
            "Самарканд Silk Wellness",
            "Samarkand Silk Wellness",
        ),
        "description": tr(
            "Samarqand markazidagi wellness markaz: yoga, spa, meditatsiya va qisqa shahar retreatlari.",
            "Wellness-центр в центре Самарканда: йога, спа, медитация и короткие городские ретриты.",
            "A wellness center in central Samarkand for yoga, spa, meditation, and short city retreats.",
        ),
        "city": "Samarqand",
        "address": tr(
            "Registon yaqinida, Universitet xiyoboni 18",
            "Рядом с Регистаном, Университетский бульвар 18",
            "Near Registan, 18 University Boulevard",
        ),
        "lat": money("39.657100"),
        "lng": money("66.974900"),
        "stars": 4,
        "phones": ["+998662220000", "+998935556677"],
        "website": "https://samarkand-silk.uzwellness.com",
        "check_in_time": time(9, 0),
        "check_out_time": time(21, 0),
        "pets_allowed": False,
        "service_animals_allowed": True,
        "min_checkin_age": 14,
        "quiet_hours_from": time(21, 30),
        "quiet_hours_to": time(8, 0),
        "payment_methods": ["cash", "bank_transfer", "uzcard", "visa", "mastercard"],
        "house_rules": tr(
            "Sessiyalarga 10 daqiqa oldin kelish so'raladi.",
            "Просим приходить за 10 минут до сессии.",
            "Please arrive 10 minutes before each session.",
        ),
        "cancellation_policy": tr(
            "Sessiyadan 24 soat oldin bepul bekor qilish mumkin.",
            "Бесплатная отмена за 24 часа до сессии.",
            "Free cancellation up to 24 hours before the session.",
        ),
        "weekly_schedule": {"daily": "09:00-21:00", "friday": "09:00-18:00"},
        "property_type": PropertyType.WELLNESS,
        "wellness_category": WellnessCategory.YOGA_RETREAT,
        "treatment_focuses": ["wellness", "neurological"],
        "year_opened": 2023,
        "languages_spoken": ["uz", "ru", "en"],
        "highlights": [
            "Small group yoga",
            "Guided meditation",
            "Historic city retreats",
        ],
        "surroundings": [
            {"name": "Registon maydoni", "type": "attraction", "distance_m": 900},
            {"name": "Siyob bozori", "type": "market", "distance_m": 1500},
        ],
        "venues": [
            {
                "name": "Silk Studio",
                "type": "yoga",
                "building": "Main floor",
                "hours": "09:00-21:00",
            },
            {
                "name": "Tea Lounge",
                "type": "lounge",
                "building": "Courtyard",
                "hours": "10:00-20:00",
            },
        ],
        "meal_schedule": [
            {
                "meal": "tea",
                "time_from": "10:00",
                "time_to": "20:00",
                "style": "herbal",
            },
            {
                "meal": "brunch",
                "time_from": "11:30",
                "time_to": "13:00",
                "style": "vegetarian",
            },
        ],
        "platform_commission_percent": money("15.00"),
        "b2b_commission_percent": money("10.00"),
        "agent_discount_tiers": [{"min_bookings": 4, "discount_percent": "6"}],
        "amenities": [
            ("wifi", AmenityCost.FREE),
            ("spa", AmenityCost.PAID),
            ("yoga", AmenityCost.FREE),
            ("restaurant", AmenityCost.PAID),
            ("airport-transfer", AmenityCost.ON_REQUEST),
        ],
        "images": [
            ("samarkand-wellness-hero.svg", True, "Courtyard yoga studio"),
            ("samarkand-yoga.svg", False, "Morning yoga session"),
            ("samarkand-spa.svg", False, "Urban spa room"),
        ],
    },
]


def humson_room(
    uz: str,
    ru: str,
    en: str,
    *,
    capacity: int,
    weekday: str,
    weekend: str,
    size_sqm: int,
    beds: list[dict],
    floor: str,
    inventory_count: int,
) -> dict:
    return {
        "name": tr(uz, ru, en),
        "description": tr(
            f"{uz}: 2025-yil 8-sentabrdan 30-dekabrgacha 20% chegirma bilan.",
            f"{ru}: 20% скидка с 8 сентября до 30 декабря 2025 года.",
            f"{en}: 20% discount from September 8 to December 30, 2025.",
        ),
        "size_sqm": size_sqm,
        "floor": floor,
        "beds": beds,
        "view": RoomView.MOUNTAIN,
        "smoking_allowed": False,
        "capacity": capacity,
        "max_adults": capacity,
        "max_children": 2 if capacity >= 2 else 1,
        "inventory_count": inventory_count,
        "base_price": money(weekday),
        "base_price_weekend": money(weekend),
        "base_currency": "UZS",
        "markup_percent": money("0.00"),
        "discount_percent": money("20.00"),
        "min_nights": 1,
        "amenities": ["wifi", "doctor", "physio", "restaurant", "pool"],
    }


HUMSON_ROOMS = [
    humson_room(
        "Standart bir kishilik",
        "Стандарт одноместный",
        "Standard Single",
        capacity=1,
        weekday="1750000.00",
        weekend="1900000.00",
        size_sqm=22,
        floor="2-3",
        inventory_count=8,
        beds=[
            {
                "label": "Single",
                "beds": [{"type": "single", "count": 1, "size_cm": "90x200"}],
            }
        ],
    ),
    humson_room(
        "Standart ikki kishilik",
        "Стандарт двухместный",
        "Standard Double",
        capacity=2,
        weekday="2950000.00",
        weekend="3200000.00",
        size_sqm=28,
        floor="2-4",
        inventory_count=14,
        beds=[
            {
                "label": "Twin",
                "beds": [{"type": "twin", "count": 2, "size_cm": "90x200"}],
            }
        ],
    ),
    humson_room(
        "Standart uch kishilik",
        "Стандарт трехместный",
        "Standard Triple",
        capacity=3,
        weekday="3650000.00",
        weekend="3900000.00",
        size_sqm=34,
        floor="2-4",
        inventory_count=10,
        beds=[
            {
                "label": "Triple",
                "beds": [{"type": "single", "count": 3, "size_cm": "90x200"}],
            }
        ],
    ),
    humson_room(
        "Standart to'rt kishilik",
        "Стандарт четырехместный",
        "Standard Quadruple",
        capacity=4,
        weekday="4300000.00",
        weekend="4800000.00",
        size_sqm=42,
        floor="3-4",
        inventory_count=8,
        beds=[
            {
                "label": "Quadruple",
                "beds": [{"type": "single", "count": 4, "size_cm": "90x200"}],
            }
        ],
    ),
    humson_room(
        "Polulyuks bir kishilik",
        "Полулюкс одноместный",
        "Junior Suite Single",
        capacity=1,
        weekday="2100000.00",
        weekend="2300000.00",
        size_sqm=30,
        floor="2-3",
        inventory_count=6,
        beds=[
            {
                "label": "Single",
                "beds": [{"type": "single", "count": 1, "size_cm": "120x200"}],
            }
        ],
    ),
    humson_room(
        "Polulyuks ikki kishilik",
        "Полулюкс двухместный",
        "Junior Suite Double",
        capacity=2,
        weekday="3650000.00",
        weekend="3900000.00",
        size_sqm=38,
        floor="3-4",
        inventory_count=6,
        beds=[
            {
                "label": "Double",
                "beds": [{"type": "double", "count": 1, "size_cm": "160x200"}],
            }
        ],
    ),
    humson_room(
        "Lyuks bir kishilik",
        "Люкс одноместный",
        "Suite Single",
        capacity=1,
        weekday="2650000.00",
        weekend="2900000.00",
        size_sqm=40,
        floor="4",
        inventory_count=4,
        beds=[
            {
                "label": "Single",
                "beds": [{"type": "queen", "count": 1, "size_cm": "160x200"}],
            }
        ],
    ),
    humson_room(
        "Lyuks ikki kishilik",
        "Люкс двухместный",
        "Suite Double",
        capacity=2,
        weekday="4850000.00",
        weekend="5300000.00",
        size_sqm=56,
        floor="4-5",
        inventory_count=5,
        beds=[
            {
                "label": "Suite",
                "beds": [{"type": "queen", "count": 1, "size_cm": "180x200"}],
            }
        ],
    ),
    humson_room(
        "Kottej to'rt kishilik",
        "Коттедж четырехместный",
        "Four-Person Cottage",
        capacity=4,
        weekday="6000000.00",
        weekend="6500000.00",
        size_sqm=72,
        floor="1",
        inventory_count=3,
        beds=[
            {
                "label": "Cottage",
                "beds": [
                    {"type": "queen", "count": 1, "size_cm": "180x200"},
                    {"type": "single", "count": 2, "size_cm": "90x200"},
                ],
            }
        ],
    ),
]


ROOMS = {
    "zomin-shifo-resort": [
        {
            "name": tr("Pine Standard", "Pine Standard", "Pine Standard"),
            "description": tr(
                "Qarag'ay tomonga qaragan sokin standart xona.",
                "Тихий стандартный номер с видом на сосны.",
                "A quiet standard room facing the pine forest.",
            ),
            "size_sqm": 28,
            "floor": "2-4",
            "beds": [
                {
                    "label": "Twin or double",
                    "beds": [
                        {"type": "twin", "count": 2, "size_cm": "90x200"},
                        {"type": "double", "count": 1, "size_cm": "160x200"},
                    ],
                }
            ],
            "view": RoomView.MOUNTAIN,
            "smoking_allowed": False,
            "capacity": 2,
            "max_adults": 2,
            "max_children": 1,
            "inventory_count": 8,
            "base_price": money("950000.00"),
            "base_price_weekend": money("1150000.00"),
            "base_currency": "UZS",
            "markup_percent": money("8.00"),
            "discount_percent": money("5.00"),
            "min_nights": 2,
            "amenities": ["wifi", "doctor", "restaurant"],
        },
        {
            "name": tr(
                "Family Forest Suite", "Семейный лесной люкс", "Family Forest Suite"
            ),
            "description": tr(
                "Oilalar uchun ikki zonali keng lyuks.",
                "Просторный двухзонный люкс для семей.",
                "A spacious two-zone suite for families.",
            ),
            "size_sqm": 52,
            "floor": "5",
            "beds": [
                {
                    "label": "Family",
                    "beds": [
                        {"type": "queen", "count": 1, "size_cm": "180x200"},
                        {"type": "sofa_bed", "count": 1, "size_cm": "140x190"},
                    ],
                }
            ],
            "view": RoomView.MOUNTAIN,
            "smoking_allowed": False,
            "capacity": 4,
            "max_adults": 3,
            "max_children": 2,
            "inventory_count": 5,
            "base_price": money("1650000.00"),
            "base_price_weekend": money("1900000.00"),
            "base_currency": "UZS",
            "markup_percent": money("10.00"),
            "discount_percent": None,
            "min_nights": 3,
            "amenities": ["wifi", "doctor", "restaurant", "parking"],
        },
    ],
    "chortoq-mineral-spa": [
        {
            "name": tr("Mineral Comfort", "Минеральный комфорт", "Mineral Comfort"),
            "description": tr(
                "Spa blokiga yaqin komfort xona.",
                "Комфортный номер рядом со спа-блоком.",
                "A comfort room close to the spa block.",
            ),
            "size_sqm": 30,
            "floor": "2,4",
            "beds": [
                {
                    "label": "Double",
                    "beds": [{"type": "double", "count": 1, "size_cm": "160x200"}],
                }
            ],
            "view": RoomView.GARDEN,
            "smoking_allowed": False,
            "capacity": 2,
            "max_adults": 2,
            "max_children": 1,
            "inventory_count": 10,
            "base_price": money("85.00"),
            "base_price_weekend": money("99.00"),
            "base_currency": "USD",
            "markup_percent": money("6.00"),
            "discount_percent": money("3.00"),
            "min_nights": 1,
            "amenities": ["wifi", "pool", "spa", "restaurant"],
        },
        {
            "name": tr("Balneo Family", "Бальнео семейный", "Balneo Family"),
            "description": tr(
                "Mineral muolajalar uchun oilaviy xona.",
                "Семейный номер для бальнеологических программ.",
                "A family room for balneology programs.",
            ),
            "size_sqm": 44,
            "floor": "3-5",
            "beds": [
                {
                    "label": "Family",
                    "beds": [
                        {"type": "queen", "count": 1, "size_cm": "180x200"},
                        {"type": "single", "count": 2, "size_cm": "90x200"},
                    ],
                }
            ],
            "view": RoomView.POOL,
            "smoking_allowed": False,
            "capacity": 4,
            "max_adults": 2,
            "max_children": 3,
            "inventory_count": 6,
            "base_price": money("130.00"),
            "base_price_weekend": money("155.00"),
            "base_currency": "USD",
            "markup_percent": money("7.00"),
            "discount_percent": None,
            "min_nights": 2,
            "amenities": ["wifi", "pool", "kids-club", "restaurant"],
        },
    ],
    "humson-buloq-health-resort": HUMSON_ROOMS,
    "chinobod-health-resort": [
        {
            "name": tr("Executive Deluxe", "Executive Deluxe", "Executive Deluxe"),
            "description": tr(
                "Biznes mehmonlar uchun ish stoli va tez internetli xona.",
                "Номер с рабочей зоной и быстрым интернетом для бизнес-гостей.",
                "A room with workspace and fast internet for business guests.",
            ),
            "size_sqm": 36,
            "floor": "6-8",
            "beds": [
                {
                    "label": "King",
                    "beds": [{"type": "king", "count": 1, "size_cm": "200x200"}],
                }
            ],
            "view": RoomView.CITY,
            "smoking_allowed": False,
            "capacity": 2,
            "max_adults": 2,
            "max_children": 1,
            "inventory_count": 7,
            "base_price": money("140.00"),
            "base_price_weekend": money("165.00"),
            "base_currency": "USD",
            "markup_percent": money("12.00"),
            "discount_percent": money("4.00"),
            "min_nights": 1,
            "amenities": ["wifi", "gym", "restaurant", "conference"],
        },
        {
            "name": tr("Garden Pet Suite", "Garden Pet Suite", "Garden Pet Suite"),
            "description": tr(
                "Bog'ga chiqishli, uy hayvoni bilan kelish mumkin bo'lgan lyuks.",
                "Люкс с выходом в сад, доступен для гостей с питомцами.",
                "A garden-access suite available for guests traveling with pets.",
            ),
            "size_sqm": 58,
            "floor": "1",
            "beds": [
                {
                    "label": "Suite",
                    "beds": [
                        {"type": "king", "count": 1, "size_cm": "200x200"},
                        {"type": "sofa_bed", "count": 1, "size_cm": "150x190"},
                    ],
                }
            ],
            "view": RoomView.GARDEN,
            "smoking_allowed": False,
            "capacity": 3,
            "max_adults": 2,
            "max_children": 2,
            "inventory_count": 4,
            "base_price": money("220.00"),
            "base_price_weekend": money("260.00"),
            "base_currency": "USD",
            "markup_percent": money("12.00"),
            "discount_percent": None,
            "min_nights": 2,
            "amenities": ["wifi", "spa", "gym", "restaurant", "parking"],
        },
    ],
}

PROGRAMS = {
    "zomin-shifo-resort": [
        {
            "name": tr(
                "Nafas olish reabilitatsiyasi",
                "Респираторная реабилитация",
                "Respiratory Rehabilitation",
            ),
            "description": tr(
                "Shifokor ko'rigi, inhalatsiya va o'rmon yurishlaridan iborat 7 kunlik dastur.",
                "7-дневная программа с осмотром врача, ингаляциями и лесными прогулками.",
                "A 7-day program with doctor checks, inhalation, and forest walks.",
            ),
            "min_nights": 7,
            "max_nights": 14,
            "duration_minutes": 60,
            "price": None,
            "currency": None,
            "instructor_name": "Dr. Dilshod Rasulov",
            "instructor_bio": tr(
                "Pulmonolog, 12 yillik tajriba.",
                "Пульмонолог, 12 лет опыта.",
                "Pulmonologist with 12 years of experience.",
            ),
            "group_size_min": 1,
            "group_size_max": 8,
            "what_to_bring": tr(
                "Qulay poyabzal va avvalgi tahlillar.",
                "Удобная обувь и предыдущие анализы.",
                "Comfortable shoes and previous test results.",
            ),
            "amenities": ["doctor", "mineral-water", "physio"],
        }
    ],
    "chortoq-mineral-spa": [
        {
            "name": tr(
                "Mineral vannalar kursi", "Курс минеральных ванн", "Mineral Bath Course"
            ),
            "description": tr(
                "Teri va bo'g'imlar uchun 10 seanslik mineral vanna kursi.",
                "Курс из 10 минеральных ванн для кожи и суставов.",
                "A 10-session mineral bath course for skin and joints.",
            ),
            "min_nights": 5,
            "max_nights": 12,
            "duration_minutes": 45,
            "price": None,
            "currency": None,
            "instructor_name": "Dr. Shahnoza Ergasheva",
            "instructor_bio": tr(
                "Balneolog mutaxassis.",
                "Специалист-бальнеолог.",
                "Balneology specialist.",
            ),
            "group_size_min": 1,
            "group_size_max": 6,
            "what_to_bring": tr(
                "Shaxsiy tibbiy karta.",
                "Личная медицинская карта.",
                "Personal medical record.",
            ),
            "amenities": ["doctor", "mineral-water", "spa"],
        }
    ],
    "humson-buloq-health-resort": [
        {
            "name": tr(
                "10 sutkalik davolash va dam olish",
                "10 суток лечения и отдыха",
                "10-Night Treatment and Leisure",
            ),
            "description": tr(
                "4 mahal ovqat, shifokor ko'rigi, laborator analizlar, fizioterapiya, gidroterapiya, ozonoterapiya va sauna kiritilgan.",
                "Включены 4-разовое питание, осмотр врача, лабораторные анализы, физиотерапия, гидротерапия, озонотерапия и сауна.",
                "Includes 4 meals a day, doctor check, lab tests, physiotherapy, hydrotherapy, ozonotherapy, and sauna.",
            ),
            "min_nights": 10,
            "max_nights": 10,
            "duration_minutes": 60,
            "price": None,
            "currency": None,
            "instructor_name": "Humson Buloq Medical Team",
            "instructor_bio": tr(
                "Gidroterapiya va fizioterapiya bo'yicha kurort shifokorlari.",
                "Курортные врачи по гидротерапии и физиотерапии.",
                "Resort doctors specializing in hydrotherapy and physiotherapy.",
            ),
            "group_size_min": 1,
            "group_size_max": 12,
            "what_to_bring": tr(
                "Pasport, bron tasdig'i va mavjud tibbiy hujjatlar.",
                "Паспорт, подтверждение брони и имеющиеся медицинские документы.",
                "Passport, booking confirmation, and available medical documents.",
            ),
            "amenities": ["doctor", "physio", "pool", "sauna", "fitobar"],
        }
    ],
    "samarkand-silk-wellness": [
        {
            "name": tr(
                "Morning Yoga Drop-in", "Утренняя йога drop-in", "Morning Yoga Drop-in"
            ),
            "description": tr(
                "90 daqiqalik kichik guruh yoga mashg'uloti.",
                "90-минутное занятие йогой в малой группе.",
                "A 90-minute small-group yoga class.",
            ),
            "min_nights": None,
            "max_nights": None,
            "duration_minutes": 90,
            "price": money("180000.00"),
            "currency": "UZS",
            "instructor_name": "Madina Sodiqova",
            "instructor_bio": tr(
                "RYT-500 sertifikatli yoga instruktori.",
                "Инструктор йоги RYT-500.",
                "RYT-500 certified yoga instructor.",
            ),
            "group_size_min": 2,
            "group_size_max": 12,
            "what_to_bring": tr(
                "Qulay kiyim va suv idishi.",
                "Удобная одежда и бутылка воды.",
                "Comfortable clothes and a water bottle.",
            ),
            "amenities": ["yoga", "wifi"],
        },
        {
            "name": tr(
                "Silk Road Meditation", "Медитация Silk Road", "Silk Road Meditation"
            ),
            "description": tr(
                "Meditatsiya, choy marosimi va yengil brunch.",
                "Медитация, чайная церемония и легкий brunch.",
                "Meditation, tea ceremony, and light brunch.",
            ),
            "min_nights": None,
            "max_nights": None,
            "duration_minutes": 150,
            "price": money("320000.00"),
            "currency": "UZS",
            "instructor_name": "Aziza Tursunova",
            "instructor_bio": tr(
                "Mindfulness mentor va retreat kuratori.",
                "Mindfulness-наставник и куратор ретритов.",
                "Mindfulness mentor and retreat curator.",
            ),
            "group_size_min": 3,
            "group_size_max": 10,
            "what_to_bring": tr(
                "Telefonni jim rejimga qo'ying.",
                "Переведите телефон в беззвучный режим.",
                "Set your phone to silent mode.",
            ),
            "amenities": ["yoga", "restaurant"],
        },
    ],
}


def medical_base_for(data: dict) -> dict:
    focus_map = {
        "respiratory": (
            "respiratory_rehab",
            tr(
                "Nafas olish reabilitatsiyasi uchun inhalatsiya, speleoterapiya va o'rmon yurishlari.",
                "Ингаляции, спелеотерапия и лесные прогулки для респираторной реабилитации.",
                "Inhalation, speleotherapy, and forest walks for respiratory rehabilitation.",
            ),
        ),
        "musculoskeletal": (
            "balneotherapy",
            tr(
                "Bo'g'im va mushaklar uchun mineral vanna va fizioterapiya kurslari.",
                "Минеральные ванны и физиотерапия для суставов и мышц.",
                "Mineral baths and physiotherapy courses for joints and muscles.",
            ),
        ),
        "cardiovascular": (
            "cardio_screening",
            tr(
                "Kardiolog nazorati, EKG va yengil kardio mashg'ulotlar.",
                "Наблюдение кардиолога, ЭКГ и легкие кардиотренировки.",
                "Cardiologist supervision, ECG, and light cardio sessions.",
            ),
        ),
        "digestive": (
            "diet_therapy",
            tr(
                "Dietolog konsultatsiyasi va individual ovqatlanish rejasi.",
                "Консультация диетолога и индивидуальный план питания.",
                "Dietitian consultation and an individual meal plan.",
            ),
        ),
        "neurological": (
            "stress_recovery",
            tr(
                "Uyqu, stress va asab tizimi tiklanishi uchun muolajalar.",
                "Процедуры для сна, стресса и восстановления нервной системы.",
                "Treatments for sleep, stress, and nervous-system recovery.",
            ),
        ),
        "dermatology": (
            "mineral_skin_care",
            tr(
                "Teri parvarishi uchun mineral suv va balchiq aplikatsiyalari.",
                "Минеральная вода и грязевые аппликации для ухода за кожей.",
                "Mineral water and mud applications for skin care.",
            ),
        ),
        "endocrine": (
            "metabolic_support",
            tr(
                "Endokrinolog nazorati va metabolik qo'llab-quvvatlash.",
                "Наблюдение эндокринолога и метаболическая поддержка.",
                "Endocrinologist supervision and metabolic support.",
            ),
        ),
        "wellness": (
            "wellness_reset",
            tr(
                "Yengil spa, massaj va kundalik harakat rejasi.",
                "Легкий спа, массаж и ежедневная программа активности.",
                "Light spa, massage, and a daily movement plan.",
            ),
        ),
    }
    procedures = [
        {
            "code": focus_map[focus][0],
            "image_url": f"/uploads/demo/procedures/{focus}.svg",
            "description": focus_map[focus][1],
        }
        for focus in data["treatment_focuses"]
        if focus in focus_map
    ]
    return {
        "description": tr(
            "Shifokor ko'rigi, bazaviy diagnostika va kunlik muolajalar jadvali kiritilgan.",
            "Включены осмотр врача, базовая диагностика и ежедневный план процедур.",
            "Includes a doctor check, basic diagnostics, and a daily treatment schedule.",
        ),
        "procedures_per_week": 12
        if data["property_type"] == PropertyType.SANATORIUM
        else 5,
        "min_age_for_treatment": data["min_checkin_age"],
        "checkups_included": 2,
        "natural_resources": [
            "mineral_water"
            if "mineral-water" in [slug for slug, _ in data["amenities"]]
            else "clean_air",
            "mountain_air"
            if data["destination"] in {"zaamin-national-park", "chimgan-mountains"}
            else "urban_wellness",
        ],
        "procedures": {
            "core": procedures[:3],
            "additional": procedures[3:],
        },
        "stay_inclusions": [
            {"min_days": 3, "inclusions": ["doctor_check", "meal_plan"]},
            {
                "min_days": 7,
                "inclusions": ["doctor_check", "diagnostics", "treatment_plan"],
            },
        ],
    }


def treatment_profile_for(data: dict) -> dict:
    titles = {
        "respiratory": tr(
            "Nafas yo'llari", "Дыхательная система", "Respiratory system"
        ),
        "musculoskeletal": tr(
            "Tayanch-harakat tizimi",
            "Опорно-двигательная система",
            "Musculoskeletal system",
        ),
        "cardiovascular": tr(
            "Yurak-qon tomir", "Сердечно-сосудистая система", "Cardiovascular system"
        ),
        "digestive": tr("Ovqat hazm qilish", "Пищеварение", "Digestive health"),
        "neurological": tr("Asab tizimi", "Нервная система", "Neurological recovery"),
        "dermatology": tr("Dermatologiya", "Дерматология", "Dermatology"),
        "endocrine": tr("Endokrinologiya", "Эндокринология", "Endocrinology"),
        "wellness": tr("Umumiy wellness", "Общий wellness", "General wellness"),
    }
    main = [
        {
            "code": focus,
            "title": titles.get(focus, tr(focus, focus, focus)),
            "description": tr(
                "Shifokor tomonidan individual reja tuziladi.",
                "Врач составляет индивидуальный план.",
                "A doctor prepares an individual plan.",
            ),
        }
        for focus in data["treatment_focuses"][:3]
    ]
    return {
        "main_indications": main,
        "additional_indications": [
            {
                "code": "fatigue_recovery",
                "title": tr(
                    "Charchoqdan tiklanish",
                    "Восстановление после усталости",
                    "Fatigue recovery",
                ),
                "description": tr(
                    "Uyqu, ovqatlanish va yengil jismoniy faollik rejasi.",
                    "Режим сна, питания и легкой физической активности.",
                    "A sleep, nutrition, and light activity routine.",
                ),
            }
        ],
        "contraindications": [
            {
                "code": "acute_condition",
                "title": tr("O'tkir holatlar", "Острые состояния", "Acute conditions"),
                "description": tr(
                    "O'tkir infeksiya yoki shifokor taqiqlagan holatlarda tavsiya etilmaydi.",
                    "Не рекомендуется при острых инфекциях или запрете врача.",
                    "Not recommended for acute infections or when restricted by a doctor.",
                ),
            }
        ],
        "diagnostics": ["doctor_consultation", "blood_pressure", "ecg"],
        "doctor_specialties": ["therapist", "physiotherapist", "dietitian"],
        "notes": tr(
            "Dastur kelish kuni shifokor ko'rigidan keyin aniqlashtiriladi.",
            "Программа уточняется после осмотра врача в день заезда.",
            "The program is finalized after the doctor's check on arrival day.",
        ),
    }


def service_group(title: dict, items: list[dict]) -> dict:
    return {"title": title, "items": items}


def service_item(
    code: str,
    title: dict,
    *,
    icon: str,
    cost: AmenityCost = AmenityCost.FREE,
    hours: str | None = None,
    location: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    return {
        "code": code,
        "title": title,
        "description": tr(
            f"{title['uz']} mavjud.",
            f"Доступно: {title['ru']}.",
            f"{title['en']} is available.",
        ),
        "is_available": True,
        "cost": cost.value,
        "hours": hours,
        "location": location,
        "icon": icon,
        "tags": tags or [],
    }


def service_matrix_for(data: dict) -> dict:
    amenity_slugs = {slug for slug, _ in data["amenities"]}
    return {
        "food_drink": service_group(
            tr("Ovqatlanish", "Питание", "Food and drink"),
            [
                service_item(
                    "restaurant",
                    tr("Restoran", "Ресторан", "Restaurant"),
                    icon="utensils",
                    hours="07:00-22:00",
                    location=data["venues"][0]["name"],
                )
            ],
        ),
        "wellness": service_group(
            tr("Wellness", "Wellness", "Wellness"),
            [
                service_item(
                    "spa" if "spa" in amenity_slugs else "walking_routes",
                    tr("Spa va tiklanish", "Спа и восстановление", "Spa and recovery"),
                    icon="sparkles",
                    cost=AmenityCost.PAID
                    if "spa" in amenity_slugs
                    else AmenityCost.FREE,
                    hours="09:00-21:00",
                )
            ],
        ),
        "medical_department": service_group(
            tr("Tibbiy bo'lim", "Медицинское отделение", "Medical department"),
            [
                service_item(
                    "doctor_supervision",
                    tr("Shifokor nazorati", "Наблюдение врача", "Doctor supervision"),
                    icon="stethoscope",
                    hours="08:00-18:00",
                )
            ],
        ),
        "front_desk": service_group(
            tr("Qabulxona", "Ресепшен", "Front desk"),
            [
                service_item(
                    "reception",
                    tr("Qabulxona", "Ресепшен", "Reception"),
                    icon="concierge-bell",
                    hours=data["weekly_schedule"].get("reception", "08:00-20:00"),
                )
            ],
        ),
        "cleaning": service_group(
            tr("Tozalik", "Уборка", "Cleaning"),
            [
                service_item(
                    "daily_cleaning",
                    tr("Kunlik tozalash", "Ежедневная уборка", "Daily cleaning"),
                    icon="sparkles",
                )
            ],
        ),
        "business": service_group(
            tr("Biznes", "Бизнес", "Business"),
            [
                service_item(
                    "conference",
                    tr(
                        "Konferensiya xizmati", "Конференц-сервис", "Conference service"
                    ),
                    icon="briefcase",
                    cost=AmenityCost.PAID,
                    location=next(
                        (
                            v["name"]
                            for v in data["venues"]
                            if v["type"] == "conference"
                        ),
                        None,
                    ),
                )
            ]
            if "conference" in amenity_slugs
            else [],
        ),
        "parking": service_group(
            tr("Avtoturargoh", "Парковка", "Parking"),
            [
                service_item(
                    "parking",
                    tr("Avtoturargoh", "Парковка", "Parking"),
                    icon="parking-circle",
                )
            ]
            if "parking" in amenity_slugs
            else [],
        ),
        "internet": service_group(
            tr("Internet", "Интернет", "Internet"),
            [
                service_item(
                    "wifi",
                    tr("Wi-Fi", "Wi-Fi", "Wi-Fi"),
                    icon="wifi",
                    tags=["rooms", "public_areas"],
                )
            ],
        ),
        "children": service_group(
            tr("Bolalar", "Дети", "Children"),
            [
                service_item(
                    "kids_club",
                    tr("Bolalar klubi", "Детский клуб", "Kids club"),
                    icon="baby",
                    hours="10:00-18:00",
                )
            ]
            if "kids-club" in amenity_slugs
            else [],
        ),
        "accessibility": service_group(
            tr("Qulay kirish", "Доступность", "Accessibility"),
            [
                service_item(
                    "service_animals",
                    tr("Xizmat hayvonlari", "Служебные животные", "Service animals"),
                    icon="accessibility",
                )
            ],
        ),
        "languages": data["languages_spoken"],
        "notes": tr(
            "Xizmatlar mavsum va bandlikka qarab o'zgarishi mumkin.",
            "Услуги могут меняться в зависимости от сезона и загрузки.",
            "Services may vary by season and occupancy.",
        ),
    }


def policies_for(data: dict) -> dict:
    breakfast_style = next(
        (
            meal["style"]
            for meal in data["meal_schedule"]
            if meal["meal"] == "breakfast"
        ),
        "set menu",
    )
    return {
        "check_in": {
            "instructions": tr(
                "Pasport va tibbiy hujjatlarni qabulxonada ko'rsating.",
                "Предъявите паспорт и медицинские документы на ресепшене.",
                "Show your passport and medical documents at reception.",
            ),
            "required_documents": ["passport", "medical_summary"],
        },
        "children": {
            "allowed": data["property_type"] == PropertyType.SANATORIUM,
            "min_age": 0,
            "treatment_min_age": data["min_checkin_age"],
        },
        "extra_bed": {
            "available": True,
            "crib_available": data["min_checkin_age"] <= 16,
            "price": "180000.00" if data["slug"] == "zomin-shifo-resort" else "18.00",
            "currency": "UZS" if data["slug"] == "zomin-shifo-resort" else "USD",
        },
        "breakfast": {
            "included": True,
            "style": breakfast_style,
            "hours": "07:00-10:00",
        },
        "pets": {
            "allowed": data["pets_allowed"],
            "service_animals_allowed": data["service_animals_allowed"],
            "fee": "25.00" if data["pets_allowed"] else None,
            "currency": "USD" if data["pets_allowed"] else None,
        },
        "cancellation": {
            "free_cancellation_until_days_before": 5,
            "penalty_percent": "50.00",
        },
        "payment": {
            "methods": data["payment_methods"],
            "deposit_required": True,
            "deposit_percent": "20.00",
        },
        "fees": {
            "mandatory_fees": ["resort_registration"],
            "optional_fees": ["airport_transfer", "additional_procedures"],
        },
    }


def promo_badges_for(data: dict) -> list[dict]:
    badges = [
        {
            "code": "doctor_checked",
            "kind": "trust",
            "title": tr("Shifokor nazorati", "Наблюдение врача", "Doctor supervised"),
            "description": tr(
                "Davolash dasturlari shifokor ko'rigidan keyin belgilanadi.",
                "Лечебные программы назначаются после осмотра врача.",
                "Treatment programs are assigned after a doctor's check.",
            ),
            "icon": "stethoscope",
            "is_active": True,
            "priority": 10,
        }
    ]
    if data["property_type"] == PropertyType.SANATORIUM:
        badges.append(
            {
                "code": "full_board_available",
                "kind": "benefit",
                "title": tr("To'liq pansion", "Полный пансион", "Full board"),
                "description": tr(
                    "Davolanishga mos ovqatlanish jadvali bor.",
                    "Есть питание по графику, подходящему для лечения.",
                    "Meal schedules are aligned with treatment stays.",
                ),
                "icon": "utensils",
                "is_active": True,
                "priority": 20,
            }
        )
    return badges


def room_features_for(data: dict) -> dict:
    is_suite = data["size_sqm"] >= 44
    return {
        "has_window": True,
        "bathroom": {
            "private": True,
            "type": "shower_and_bathtub" if is_suite else "shower",
            "bidet": is_suite,
            "toiletries": True,
            "hairdryer": True,
            "bathrobe": is_suite,
            "slippers": True,
        },
        "climate": {"air_conditioning": True, "heating": True},
        "kitchen": {
            "refrigerator": True,
            "minibar": data["base_currency"] == "USD",
            "kettle": True,
            "kitchenette": is_suite,
        },
        "accessibility": {
            "wheelchair_accessible": data["floor"] == "1",
            "roll_in_shower": data["floor"] == "1",
            "grab_bars": data["floor"] == "1",
            "visual_alarm": False,
        },
        "safety": {"safe": True, "smoke_detector": True, "smart_lock": True},
        "entertainment": {
            "tv": True,
            "smart_tv": data["base_currency"] == "USD",
            "satellite_channels": True,
        },
        "comfort": {
            "balcony": data["view"]
            in {RoomView.MOUNTAIN, RoomView.GARDEN, RoomView.POOL},
            "terrace": data["floor"] == "1",
            "desk": True,
            "sofa": is_suite,
            "carpet": data["view"] == RoomView.MOUNTAIN,
        },
        "highlights": [
            "spacious" if is_suite else "compact_comfort",
            f"{data['view'].value}_view" if data["view"] else "quiet_room",
        ],
    }


async def clear_demo_data(db) -> None:
    models = [
        Payment,
        Notification,
        BookingExtraBed,
        TransferRequest,
        VisaRequest,
        Booking,
        SanatoriumReview,
        PackageItem,
        Package,
        ExtraBedConfig,
        RoomAvailability,
        RatePlan,
        RoomPricePeriod,
        RoomImage,
        Room,
        TreatmentProgram,
        SanatoriumAmenity,
        SanatoriumImage,
        Sanatorium,
        Amenity,
        RefreshToken,
        User,
    ]
    for model in models:
        await db.execute(delete(model))


async def ensure_regions(db) -> dict[str, Region]:
    existing = {
        row.slug: row for row in (await db.execute(select(Region))).scalars().all()
    }
    for slug, name in REGIONS:
        if slug not in existing:
            region = Region(slug=slug, name=name, is_active=True)
            db.add(region)
            await db.flush()
            existing[slug] = region
    return existing


async def ensure_destinations(db) -> dict[str, Destination]:
    existing = {
        row.slug: row for row in (await db.execute(select(Destination))).scalars().all()
    }
    for data in DESTINATIONS:
        if data["slug"] not in existing:
            demo_media_file(data["hero_image_url"], data["name"]["en"])
            destination = Destination(
                slug=data["slug"],
                name=data["name"],
                tagline=data["tagline"],
                description=data["description"],
                hero_image_url=data["hero_image_url"],
                lat=data["lat"],
                lng=data["lng"],
                is_active=True,
            )
            db.add(destination)
            await db.flush()
            existing[destination.slug] = destination
    return existing


async def create_users(db) -> dict[str, User]:
    users = {}
    for data in USERS:
        user = User(
            email=data["email"],
            password_hash=hash_password(data["password"]),
            role=data["role"],
            full_name=data["full_name"],
            phone=data["phone"],
            is_active=True,
        )
        db.add(user)
        users[user.email] = user
    await db.flush()
    return users


async def create_amenities(db) -> dict[str, Amenity]:
    amenities = {}
    for slug, category, icon, name in AMENITIES:
        amenity = Amenity(
            name=name,
            description=tr(
                f"{name['uz']} xizmati mavjud.",
                f"Доступна услуга: {name['ru']}.",
                f"{name['en']} is available.",
            ),
            category=category,
            icon=icon,
        )
        db.add(amenity)
        amenities[slug] = amenity
    await db.flush()
    return amenities


async def create_sanatoriums(
    db,
    *,
    users: dict[str, User],
    amenities: dict[str, Amenity],
    regions: dict[str, Region],
    destinations: dict[str, Destination],
) -> dict[str, Sanatorium]:
    sanatoriums = {}
    for data in SANATORIUMS:
        treatment_profile = data.get("treatment_profile") or treatment_profile_for(data)
        promo_badges = data.get("promo_badges") or promo_badges_for(data)
        service_matrix = data.get("service_matrix") or service_matrix_for(data)
        medical_base = data.get("medical_base") or medical_base_for(data)
        policies = data.get("policies") or policies_for(data)
        for items in (medical_base.get("procedures") or {}).values():
            for procedure in items:
                if image_url := procedure.get("image_url"):
                    demo_media_file(
                        image_url,
                        procedure["description"].get("en") or procedure["code"],
                    )
        san = Sanatorium(
            name=data["name"],
            slug=data["slug"],
            description=data["description"],
            city=data["city"],
            region_id=regions[data["region"]].id,
            destination_id=destinations[data["destination"]].id,
            address=data["address"],
            lat=data["lat"],
            lng=data["lng"],
            phones=data["phones"],
            website=data["website"],
            check_in_time=data["check_in_time"],
            check_out_time=data["check_out_time"],
            pets_allowed=data["pets_allowed"],
            service_animals_allowed=data["service_animals_allowed"],
            min_checkin_age=data["min_checkin_age"],
            quiet_hours_from=data["quiet_hours_from"],
            quiet_hours_to=data["quiet_hours_to"],
            payment_methods=data["payment_methods"],
            house_rules=data["house_rules"],
            cancellation_policy=data["cancellation_policy"],
            weekly_schedule=data["weekly_schedule"],
            stars=data["stars"],
            property_type=data["property_type"],
            wellness_category=data["wellness_category"],
            treatment_focuses=data["treatment_focuses"],
            year_opened=data["year_opened"],
            languages_spoken=data["languages_spoken"],
            highlights=data["highlights"],
            surroundings=data["surroundings"],
            venues=data["venues"],
            meal_schedule=data["meal_schedule"],
            treatment_profile=treatment_profile,
            promo_badges=promo_badges,
            service_matrix=service_matrix,
            medical_base=medical_base,
            policies=policies,
            platform_commission_percent=data["platform_commission_percent"],
            b2b_commission_percent=data["b2b_commission_percent"],
            agent_discount_tiers=data["agent_discount_tiers"],
            avg_rating=Decimal("0.00"),
            review_count=0,
            status=SanatoriumStatus.APPROVED,
            admin_user_id=users[data["admin"]].id,
        )
        db.add(san)
        await db.flush()

        for order, (filename, primary, caption) in enumerate(data["images"]):
            url = f"/uploads/demo/sanatoriums/{data['slug']}/{filename}"
            demo_media_file(url, caption)
            db.add(
                SanatoriumImage(
                    sanatorium_id=san.id,
                    url=url,
                    order=order,
                    is_primary=primary,
                    is_360=order == 2,
                    category="exterior"
                    if primary
                    else "treatment"
                    if "treatment" in filename
                    else "surroundings",
                    caption=caption,
                    caption_i18n=tr(
                        caption,
                        caption,
                        caption,
                    ),
                    alt_text=tr(
                        caption,
                        caption,
                        caption,
                    ),
                    tags=[data["slug"], "primary" if primary else "gallery"],
                )
            )
        for slug, cost in data["amenities"]:
            db.add(
                SanatoriumAmenity(
                    sanatorium_id=san.id,
                    amenity_id=amenities[slug].id,
                    cost=cost,
                    is_available=True,
                )
            )
        sanatoriums[san.slug] = san
    await db.flush()
    return sanatoriums


async def create_rooms(
    db,
    *,
    sanatoriums: dict[str, Sanatorium],
    amenities: dict[str, Amenity],
    today: date,
) -> dict[str, list[Room]]:
    rooms_by_slug: dict[str, list[Room]] = {}
    for san_slug, templates in ROOMS.items():
        san = sanatoriums[san_slug]
        rooms_by_slug[san_slug] = []
        for index, data in enumerate(templates, start=1):
            room = Room(
                sanatorium_id=san.id,
                name=data["name"],
                description=data["description"],
                size_sqm=data["size_sqm"],
                floor=data["floor"],
                beds=data["beds"],
                view=data["view"],
                smoking_allowed=data["smoking_allowed"],
                capacity=data["capacity"],
                max_adults=data["max_adults"],
                max_children=data["max_children"],
                inventory_count=data["inventory_count"],
                base_price=data["base_price"],
                base_price_weekend=data["base_price_weekend"],
                base_currency=data["base_currency"],
                markup_percent=data["markup_percent"],
                discount_percent=data["discount_percent"],
                min_nights=data["min_nights"],
                room_features=room_features_for(data),
                is_active=True,
                amenities=[amenities[slug] for slug in data["amenities"]],
            )
            db.add(room)
            await db.flush()

            bedroom_url = f"/uploads/demo/rooms/{san_slug}/room-{index}-1.svg"
            tour_url = f"/uploads/demo/rooms/{san_slug}/room-{index}-tour.svg"
            demo_media_file(bedroom_url, f"{data['name']['en']} bedroom")
            demo_media_file(tour_url, f"{data['name']['en']} 360 tour")
            db.add_all(
                [
                    RoomImage(
                        room_id=room.id,
                        url=bedroom_url,
                        order=0,
                        is_primary=True,
                        is_video=False,
                        is_360=False,
                        category="bedroom",
                        caption=f"{data['name']['en']} bedroom",
                        caption_i18n=tr(
                            f"{data['name']['uz']} yotoq zonasi",
                            f"Спальная зона {data['name']['ru']}",
                            f"{data['name']['en']} bedroom",
                        ),
                        alt_text=tr(
                            f"{data['name']['uz']} xonasi",
                            f"Номер {data['name']['ru']}",
                            f"{data['name']['en']} room",
                        ),
                        tags=[san_slug, "room", "bedroom"],
                    ),
                    RoomImage(
                        room_id=room.id,
                        url=tour_url,
                        order=1,
                        is_primary=False,
                        is_video=False,
                        is_360=True,
                        category="tour",
                        caption=f"{data['name']['en']} video tour",
                        caption_i18n=tr(
                            f"{data['name']['uz']} video turi",
                            f"Видео-тур {data['name']['ru']}",
                            f"{data['name']['en']} video tour",
                        ),
                        alt_text=tr(
                            f"{data['name']['uz']} bo'yicha video tur",
                            f"Видео-тур по номеру {data['name']['ru']}",
                            f"Video tour of {data['name']['en']}",
                        ),
                        tags=[san_slug, "room", "tour", "360"],
                    ),
                ]
            )
            db.add_all(
                [
                    RatePlan(
                        room_id=room.id,
                        name=tr("Moslashuvchan tarif", "Гибкий тариф", "Flexible rate"),
                        board=BoardType.FULL_BOARD,
                        board_optional=False,
                        board_price=None,
                        board_guests=room.capacity,
                        refundable=True,
                        free_cancellation_days=5,
                        cancellation_penalty_percent=money("50.00"),
                        cancellation_penalty_amount=None,
                        payment_timing=PaymentTiming.DEPOSIT,
                        confirmation=ConfirmationType.INSTANT,
                        price_adjustment_percent=None,
                        promo_label="Early wellness",
                        promo_percent=money("7.00"),
                        promo_starts_at=utc_now(),
                        promo_ends_at=utc_now() + timedelta(days=45),
                        min_nights=room.min_nights,
                        max_nights=21,
                        is_active=True,
                    ),
                    RatePlan(
                        room_id=room.id,
                        name=tr(
                            "Qaytarilmaydigan tarif",
                            "Невозвратный тариф",
                            "Non-refundable rate",
                        ),
                        board=BoardType.BREAKFAST,
                        board_optional=True,
                        board_price=money("12.00")
                        if room.base_currency == "USD"
                        else money("120000.00"),
                        board_guests=2,
                        refundable=False,
                        free_cancellation_days=None,
                        cancellation_penalty_percent=money("100.00"),
                        cancellation_penalty_amount=None,
                        payment_timing=PaymentTiming.PREPAY,
                        confirmation=ConfirmationType.INSTANT,
                        price_adjustment_percent=money("-8.00"),
                        promo_label=None,
                        promo_percent=None,
                        promo_starts_at=None,
                        promo_ends_at=None,
                        min_nights=room.min_nights,
                        max_nights=14,
                        is_active=True,
                    ),
                ]
            )
            db.add(
                RoomPricePeriod(
                    room_id=room.id,
                    label="Summer high season",
                    date_from=today + timedelta(days=30),
                    date_to=today + timedelta(days=95),
                    base_price=(room.base_price * Decimal("1.18")).quantize(
                        Decimal("0.01")
                    ),
                    base_price_weekend=(
                        room.base_price_weekend * Decimal("1.18")
                    ).quantize(Decimal("0.01"))
                    if room.base_price_weekend is not None
                    else None,
                    discount_percent=money("2.00"),
                )
            )
            for offset in range(1, 61):
                blocked = (
                    1 if offset in {12, 13, 35} and room.inventory_count > 2 else 0
                )
                booked = 1 if offset in {8, 9, 10, 28} else 0
                db.add(
                    RoomAvailability(
                        room_id=room.id,
                        date=today + timedelta(days=offset),
                        units_blocked=blocked,
                        units_booked=booked,
                    )
                )
            rooms_by_slug[san_slug].append(room)
    await db.flush()
    return rooms_by_slug


async def create_programs(
    db,
    *,
    sanatoriums: dict[str, Sanatorium],
    amenities: dict[str, Amenity],
) -> dict[str, list[TreatmentProgram]]:
    programs_by_slug = {}
    for san_slug, templates in PROGRAMS.items():
        san = sanatoriums[san_slug]
        programs_by_slug[san_slug] = []
        for data in templates:
            program = TreatmentProgram(
                sanatorium_id=san.id,
                name=data["name"],
                description=data["description"],
                min_nights=data["min_nights"],
                max_nights=data["max_nights"],
                duration_minutes=data["duration_minutes"],
                price=data["price"],
                currency=data["currency"],
                instructor_name=data["instructor_name"],
                instructor_bio=data["instructor_bio"],
                group_size_min=data["group_size_min"],
                group_size_max=data["group_size_max"],
                what_to_bring=data["what_to_bring"],
                is_active=True,
                amenities=[amenities[slug] for slug in data["amenities"]],
            )
            db.add(program)
            programs_by_slug[san_slug].append(program)
    await db.flush()
    return programs_by_slug


async def create_extra_beds(
    db, sanatoriums: dict[str, Sanatorium]
) -> dict[str, ExtraBedConfig]:
    configs = {}
    for san_slug, san in sanatoriums.items():
        if san_slug == "humson-buloq-health-resort":
            humson_configs = [
                (
                    tr(
                        "4-10 yosh bolalar uchun qo'shimcha joy",
                        "Дополнительное размещение для детей 4-10 лет",
                        "Extra placement for children 4-10",
                    ),
                    money("500000.00"),
                ),
                (
                    tr(
                        "10 yoshdan katta bolalar uchun qo'shimcha joy",
                        "Дополнительное размещение для детей старше 10 лет",
                        "Extra placement for children over 10",
                    ),
                    money("1000000.00"),
                ),
            ]
            for index, (name, price) in enumerate(humson_configs):
                config = ExtraBedConfig(
                    sanatorium_id=san.id,
                    name=name,
                    description=tr(
                        "Ovqatlanish, qo'shimcha matras va yotoq anjomlari kiritilgan.",
                        "Включены питание, дополнительный матрас и постельные принадлежности.",
                        "Meals, an extra mattress, and bedding are included.",
                    ),
                    price_per_night=price,
                    currency="UZS",
                    max_count=4,
                    is_active=True,
                )
                db.add(config)
                if index == 0:
                    configs[san_slug] = config
            continue
        currency = "UZS" if san_slug == "zomin-shifo-resort" else "USD"
        price = money("180000.00") if currency == "UZS" else money("18.00")
        config = ExtraBedConfig(
            sanatorium_id=san.id,
            name=tr("Qo'shimcha o'rin", "Дополнительное место", "Extra bed"),
            description=tr(
                "Kattalar yoki bolalar uchun yig'ma qo'shimcha o'rin.",
                "Раскладное дополнительное место для взрослого или ребенка.",
                "A foldaway extra bed for an adult or child.",
            ),
            price_per_night=price,
            currency=currency,
            max_count=3,
            is_active=True,
        )
        db.add(config)
        configs[san_slug] = config
    await db.flush()
    return configs


async def create_packages(
    db, *, sanatoriums: dict[str, Sanatorium], rooms_by_slug: dict[str, list[Room]]
) -> dict[str, Package]:
    package_specs = [
        {
            "slug": "zaamin-respiratory-retreat-7n",
            "sanatorium": "zomin-shifo-resort",
            "room_index": 0,
            "title": tr(
                "Zomin 7 kecha nafas retreati",
                "7 ночей дыхательного ретрита в Заамине",
                "Zaamin 7-Night Respiratory Retreat",
            ),
            "description": tr(
                "Yashash, to'liq pansion, shifokor ko'rigi, inhalatsiya va transfer kiritilgan.",
                "Проживание, полный пансион, осмотр врача, ингаляции и трансфер включены.",
                "Accommodation, full board, doctor check, inhalation, and transfer included.",
            ),
            "duration_nights": 7,
            "base_price": money("6800000.00"),
            "currency": "UZS",
            "hero": "/uploads/demo/packages/zaamin-retreat.svg",
            "is_featured": True,
            "display_order": 1,
        },
        {
            "slug": "chinobod-diagnostics-weekend",
            "sanatorium": "chinobod-health-resort",
            "room_index": 0,
            "title": tr(
                "Chinobod diagnostika weekend",
                "Диагностический weekend в Чинободе",
                "Chinobod Diagnostics Weekend",
            ),
            "description": tr(
                "2 kecha yashash, diagnostika paketi, spa va aeroport transferi.",
                "2 ночи проживания, диагностика, спа и трансфер из аэропорта.",
                "Two nights, diagnostics package, spa, and airport transfer.",
            ),
            "duration_nights": 2,
            "base_price": money("520.00"),
            "currency": "USD",
            "hero": "/uploads/demo/packages/chinobod-weekend.svg",
            "is_featured": True,
            "display_order": 2,
        },
    ]
    packages = {}
    for spec in package_specs:
        room = rooms_by_slug[spec["sanatorium"]][spec["room_index"]]
        demo_media_file(spec["hero"], spec["title"]["en"])
        package = Package(
            slug=spec["slug"],
            title=spec["title"],
            description=spec["description"],
            hero_image_url=spec["hero"],
            duration_nights=spec["duration_nights"],
            base_price=spec["base_price"],
            currency=spec["currency"],
            sanatorium_id=sanatoriums[spec["sanatorium"]].id,
            room_id=room.id,
            is_active=True,
            is_featured=spec["is_featured"],
            display_order=spec["display_order"],
        )
        db.add(package)
        await db.flush()
        db.add_all(
            [
                PackageItem(
                    package_id=package.id,
                    item_type=PackageItemType.TREATMENT,
                    title=tr(
                        "Davolash dasturi", "Лечебная программа", "Treatment program"
                    ),
                    description=tr(
                        "Shifokor tuzgan kunlik muolajalar.",
                        "Ежедневные процедуры по назначению врача.",
                        "Daily treatments prescribed by a doctor.",
                    ),
                    is_included=True,
                    extra_price=None,
                    display_order=1,
                ),
                PackageItem(
                    package_id=package.id,
                    item_type=PackageItemType.TRANSFER,
                    title=tr("Transfer", "Трансфер", "Transfer"),
                    description=tr(
                        "Aeroport yoki vokzaldan kutib olish.",
                        "Встреча из аэропорта или вокзала.",
                        "Pickup from the airport or railway station.",
                    ),
                    is_included=True,
                    extra_price=None,
                    display_order=2,
                ),
                PackageItem(
                    package_id=package.id,
                    item_type=PackageItemType.EXCURSION,
                    title=tr(
                        "Mahalliy ekskursiya", "Местная экскурсия", "Local excursion"
                    ),
                    description=tr(
                        "Yarim kunlik gid xizmati.",
                        "Полдня с гидом.",
                        "A half-day guided tour.",
                    ),
                    is_included=False,
                    extra_price=money("45.00")
                    if spec["currency"] == "USD"
                    else money("450000.00"),
                    display_order=3,
                ),
            ]
        )
        packages[package.slug] = package
    await db.flush()
    return packages


async def create_reviews(
    db, *, sanatoriums: dict[str, Sanatorium], users: dict[str, User]
) -> None:
    review_specs = [
        (
            "zomin-shifo-resort",
            "ali@gmail.com",
            "Ali Karimov",
            "Kazakhstan",
            "family",
            5,
            "Tog' havosi va davolash rejasi juda yaxshi tashkil qilingan.",
        ),
        (
            "zomin-shifo-resort",
            "zulfiya@gmail.com",
            "Zulfiya Yusupova",
            "Kyrgyzstan",
            "couple",
            4,
            "Xodimlar e'tiborli, ovqatlanish rejasi aniq.",
        ),
        (
            "chortoq-mineral-spa",
            "malika@gmail.com",
            "Malika Rahimova",
            "Uzbekistan",
            "solo",
            5,
            "Mineral vannalar va spa zonasi yoqdi.",
        ),
        (
            "chinobod-health-resort",
            "ali@gmail.com",
            "Ali Karimov",
            "Kazakhstan",
            "business",
            5,
            "Diagnostika tez, xona qulay va internet barqaror.",
        ),
        (
            "samarkand-silk-wellness",
            "zulfiya@gmail.com",
            "Zulfiya Yusupova",
            "Kyrgyzstan",
            "solo",
            5,
            "Yoga sessiyasi kichik guruhda professional o'tdi.",
        ),
    ]
    rating_sum: dict[str, int] = {slug: 0 for slug in sanatoriums}
    rating_count: dict[str, int] = {slug: 0 for slug in sanatoriums}
    category_sums: dict[str, dict[str, int]] = {
        slug: {
            "cleanliness": 0,
            "amenities": 0,
            "location": 0,
            "service": 0,
            "treatment": 0,
            "value": 0,
            "food": 0,
        }
        for slug in sanatoriums
    }
    for san_slug, email, name, country, traveler_type, rating, body in review_specs:
        value_rating = max(rating - 1, 1)
        db.add(
            SanatoriumReview(
                sanatorium_id=sanatoriums[san_slug].id,
                user_id=users[email].id,
                reviewer_name=name,
                reviewer_country=country,
                traveler_type=traveler_type,
                rating=rating,
                cleanliness=rating,
                amenities=rating,
                location=rating,
                service=rating,
                treatment=rating,
                value=value_rating,
                food=rating,
                body=body,
                is_visible=True,
            )
        )
        rating_sum[san_slug] += rating
        rating_count[san_slug] += 1
        category_sums[san_slug]["cleanliness"] += rating
        category_sums[san_slug]["amenities"] += rating
        category_sums[san_slug]["location"] += rating
        category_sums[san_slug]["service"] += rating
        category_sums[san_slug]["treatment"] += rating
        category_sums[san_slug]["value"] += value_rating
        category_sums[san_slug]["food"] += rating
    for slug, san in sanatoriums.items():
        count = rating_count[slug]
        san.review_count = count
        san.avg_rating = (
            (Decimal(rating_sum[slug]) / Decimal(count)).quantize(Decimal("0.01"))
            if count
            else None
        )
        san.rating_breakdown = (
            {
                key: str((Decimal(value) / Decimal(count)).quantize(Decimal("0.01")))
                for key, value in category_sums[slug].items()
            }
            if count
            else {}
        )


async def create_bookings(
    db,
    *,
    users: dict[str, User],
    rooms_by_slug: dict[str, list[Room]],
    programs_by_slug: dict[str, list[TreatmentProgram]],
    packages: dict[str, Package],
    extra_beds: dict[str, ExtraBedConfig],
    today: date,
) -> None:
    room = rooms_by_slug["zomin-shifo-resort"][0]
    rate_plan = (
        await db.execute(select(RatePlan).where(RatePlan.room_id == room.id).limit(1))
    ).scalar_one()
    check_in = today + timedelta(days=14)
    check_out = check_in + timedelta(days=3)
    nightly = calculate_night_price(
        room.base_price,
        room.base_price_weekend,
        room.markup_percent,
        room.discount_percent,
        False,
    )
    base_total = nightly * 3
    extra = extra_beds["zomin-shifo-resort"]
    extra_total = extra.price_per_night * 3
    booking = Booking(
        user_id=users["ali@gmail.com"].id,
        room_id=room.id,
        rate_plan_id=rate_plan.id,
        booking_type=BookingType.ROOM,
        check_in=check_in,
        check_out=check_out,
        guests=3,
        rooms_count=1,
        status=BookingStatus.CONFIRMED,
        final_price=base_total + extra_total,
        currency=room.base_currency,
        is_b2b=False,
        guest_details=[
            {"full_name": "Ali Karimov", "age": 34},
            {"full_name": "Madina Karimova", "age": 32},
            {"full_name": "Yusuf Karimov", "age": 8},
        ],
        commission_snapshot=(base_total * Decimal("0.12")).quantize(Decimal("0.01")),
        commission_percent_snapshot=Decimal("12.00"),
        agent_discount_percent_snapshot=None,
        board=rate_plan.board,
        refundable=rate_plan.refundable,
        free_cancellation_days=rate_plan.free_cancellation_days,
        cancellation_penalty_percent=rate_plan.cancellation_penalty_percent,
        cancellation_penalty_amount=rate_plan.cancellation_penalty_amount,
        original_price=base_total,
        promo_percent_snapshot=rate_plan.promo_percent,
        payment_timing=rate_plan.payment_timing,
    )
    db.add(booking)
    await db.flush()
    db.add(
        BookingExtraBed(
            booking_id=booking.id,
            config_id=extra.id,
            name_snapshot=extra.name,
            price_per_night_snapshot=extra.price_per_night,
            currency=extra.currency,
            count=1,
            total_price=extra_total,
        )
    )
    db.add_all(
        [
            Notification(
                booking_id=booking.id,
                type="booking_created",
                channel="email",
                status="sent",
            ),
            Payment(
                booking_id=booking.id,
                method=PaymentMethod.PAYME,
                status=PaymentStatus.PAID,
                amount=booking.final_price,
                currency=booking.currency,
                merchant_trans_id=f"demo-{booking.code}",
                provider_payment_id="payme-demo-001",
                raw_payload={"source": "demo_data", "status": "paid"},
                paid_at=utc_now(),
            ),
        ]
    )

    program = programs_by_slug["samarkand-silk-wellness"][0]
    session_booking = Booking(
        user_id=users["zulfiya@gmail.com"].id,
        program_id=program.id,
        booking_type=BookingType.SESSION,
        check_in=today + timedelta(days=9),
        check_out=today + timedelta(days=9),
        guests=2,
        rooms_count=1,
        status=BookingStatus.CONFIRMED,
        final_price=program.price * 2,
        currency=program.currency,
        is_b2b=False,
        guest_details=[
            {"full_name": "Zulfiya Yusupova"},
            {"full_name": "Aida Yusupova"},
        ],
        commission_snapshot=(program.price * 2 * Decimal("0.15")).quantize(
            Decimal("0.01")
        ),
        commission_percent_snapshot=Decimal("15.00"),
    )
    db.add(session_booking)

    package = packages["chinobod-diagnostics-weekend"]
    package_booking = Booking(
        user_id=users["agent@uzwellness.com"].id,
        room_id=package.room_id,
        package_id=package.id,
        booking_type=BookingType.PACKAGE,
        check_in=today + timedelta(days=21),
        check_out=today + timedelta(days=23),
        guests=2,
        rooms_count=1,
        status=BookingStatus.CONFIRMED,
        final_price=money("998.40"),
        currency=package.currency,
        is_b2b=True,
        guest_details=[
            {"full_name": "B2B Client One"},
            {"full_name": "B2B Client Two"},
        ],
        commission_snapshot=money("79.87"),
        commission_percent_snapshot=money("8.00"),
        agent_discount_percent_snapshot=money("4.00"),
        payment_timing=PaymentTiming.PREPAY,
    )
    db.add(package_booking)


async def create_requests(db, *, users: dict[str, User], today: date) -> None:
    db.add_all(
        [
            VisaRequest(
                user_id=users["ali@gmail.com"].id,
                full_name="Ali Karimov",
                citizenship="Kazakhstan",
                passport_number="KZ-DEMO-123456",
                date_of_birth=date(1991, 5, 14),
                arrival_date=today + timedelta(days=30),
                departure_date=today + timedelta(days=40),
                purpose=VisaPurpose.TREATMENT,
                status=VisaStatus.PROCESSING,
                admin_notes="Invitation letter draft prepared.",
                contact_email="ali@gmail.com",
                contact_phone=users["ali@gmail.com"].phone,
            ),
            VisaRequest(
                user_id=users["zulfiya@gmail.com"].id,
                full_name="Zulfiya Yusupova",
                citizenship="Kyrgyzstan",
                passport_number="KG-DEMO-765432",
                date_of_birth=date(1988, 11, 3),
                arrival_date=today + timedelta(days=18),
                departure_date=today + timedelta(days=24),
                purpose=VisaPurpose.TOURISM,
                status=VisaStatus.ISSUED,
                admin_notes="Issued for demo workflow.",
                contact_email="zulfiya@gmail.com",
                contact_phone=users["zulfiya@gmail.com"].phone,
            ),
            TransferRequest(
                user_id=users["ali@gmail.com"].id,
                booking_id=None,
                direction=TransferDirection.ROUND_TRIP,
                pickup_location="Tashkent International Airport, Terminal 2",
                dropoff_location="Zomin Shifo Resort",
                flight_number="HY-DEMO-614",
                flight_time=utc_now() + timedelta(days=14, hours=5),
                return_flight_number="HY-DEMO-615",
                return_flight_time=utc_now() + timedelta(days=17, hours=9),
                passengers_count=3,
                vehicle_type=VehicleType.MINIVAN,
                price=money("95.00"),
                currency="USD",
                status=TransferStatus.CONFIRMED,
                driver_name="Rustam Akhmedov",
                driver_phone="+998901010101",
                notes="Child seat requested.",
                admin_notes="Driver assigned.",
                contact_phone=users["ali@gmail.com"].phone,
            ),
        ]
    )


async def main() -> None:
    today = date.today()
    async with SessionLocal() as db:
        await clear_demo_data(db)

        rate = (
            await db.execute(select(ExchangeRate).where(ExchangeRate.pair == "USD_UZS"))
        ).scalar_one_or_none()
        if rate is None:
            db.add(
                ExchangeRate(
                    pair="USD_UZS",
                    rate=USD_UZS,
                    valid_from=utc_now(),
                )
            )
        else:
            rate.rate = USD_UZS
            rate.valid_from = utc_now()

        regions = await ensure_regions(db)
        destinations = await ensure_destinations(db)
        users = await create_users(db)
        amenities = await create_amenities(db)
        sanatoriums = await create_sanatoriums(
            db,
            users=users,
            amenities=amenities,
            regions=regions,
            destinations=destinations,
        )
        rooms_by_slug = await create_rooms(
            db, sanatoriums=sanatoriums, amenities=amenities, today=today
        )
        programs_by_slug = await create_programs(
            db,
            sanatoriums=sanatoriums,
            amenities=amenities,
        )
        extra_beds = await create_extra_beds(db, sanatoriums)
        packages = await create_packages(
            db, sanatoriums=sanatoriums, rooms_by_slug=rooms_by_slug
        )
        await create_reviews(db, sanatoriums=sanatoriums, users=users)
        await create_bookings(
            db,
            users=users,
            rooms_by_slug=rooms_by_slug,
            programs_by_slug=programs_by_slug,
            packages=packages,
            extra_beds=extra_beds,
            today=today,
        )
        await create_requests(db, users=users, today=today)

        await db.commit()

    print("Demo data reset complete.")
    print(f"super_admin: {SUPER_ADMIN_EMAIL} / {DEFAULT_PASSWORD}")
    print(f"admin:       zaamin@uzwellness.com / {DEFAULT_PASSWORD}")
    print(f"agent:       agent@uzwellness.com / {AGENT_PASSWORD}")
    print(f"customer:    ali@gmail.com / {CUSTOMER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
