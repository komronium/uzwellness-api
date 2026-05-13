"""Seed Humson Buloq sanatorium with real price-list data (Sep–Dec 2025).

Idempotent: safe to run multiple times.

Usage:
    uv run python -m scripts.humson_buloq
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.amenity import Amenity, TreatmentProgram
from app.models.availability import RoomAvailability
from app.models.extra_bed import ExtraBedConfig
from app.models.room import RoomCategory
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole

# ── admin ──────────────────────────────────────────────────────────────────

ADMIN = {
    "email": "humsonbuloq@uzwellness.com",
    "password": "Admin123!",
    "full_name": "Humson Buloq Admin",
}

# ── sanatorium ─────────────────────────────────────────────────────────────

SANATORIUM = {
    "name": "Humson Buloq",
    "slug": "humson-buloq",
    "description": {
        "uz": "Toshkent viloyatidagi Humson Buloq sanatoriy-kurort majmuasi. "
              "Shifobaxsh buloq suvi va zamonaviy tibbiy muolajalar.",
        "ru": "Санаторно-курортный комплекс Хумсон Булоқ в Ташкентской области. "
              "Целебная минеральная вода и современные медицинские процедуры.",
        "en": "Humson Buloq resort and spa complex in Tashkent region. "
              "Healing mineral water and modern medical treatments.",
    },
    "city": "Toshkent viloyati",
    "address": "Bostanliq tumani, Humson qishlog'i",
    "lat": Decimal("41.6833"),
    "lng": Decimal("70.0167"),
    "phone": "+998991006000",
    "stars": 4,
    "treatment_focuses": ["musculoskeletal", "cardiovascular", "respiratory", "digestive", "wellness"],
}

# ── room categories ────────────────────────────────────────────────────────
# All prices in UZS per night. discount_percent=20 reflects the 20% скидка column.

ROOMS = [
    {
        "key": "std-1",
        "name": {"uz": "Standart bir kishilik", "ru": "Стандарт одноместный", "en": "Standard Single"},
        "capacity": 1,
        "base_price": Decimal("1750000"),
        "base_price_weekend": Decimal("1900000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "std-2",
        "name": {"uz": "Standart ikki kishilik", "ru": "Стандарт двухместный", "en": "Standard Double"},
        "capacity": 2,
        "base_price": Decimal("2950000"),
        "base_price_weekend": Decimal("3200000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "std-3",
        "name": {"uz": "Standart uch kishilik", "ru": "Стандарт трехместный", "en": "Standard Triple"},
        "capacity": 3,
        "base_price": Decimal("3650000"),
        "base_price_weekend": Decimal("3900000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "std-4",
        "name": {"uz": "Standart to'rt kishilik", "ru": "Стандарт четырехместный", "en": "Standard Quad"},
        "capacity": 4,
        "base_price": Decimal("4300000"),
        "base_price_weekend": Decimal("4800000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "semi-1",
        "name": {"uz": "Polulyuks bir kishilik", "ru": "Полулюкс одноместный", "en": "Semi-Suite Single"},
        "capacity": 1,
        "base_price": Decimal("2100000"),
        "base_price_weekend": Decimal("2300000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "semi-2",
        "name": {"uz": "Polulyuks ikki kishilik", "ru": "Полулюкс двухместный", "en": "Semi-Suite Double"},
        "capacity": 2,
        "base_price": Decimal("3650000"),
        "base_price_weekend": Decimal("3900000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "suite-1",
        "name": {"uz": "Lyuks bir kishilik", "ru": "Люкс одноместный", "en": "Suite Single"},
        "capacity": 1,
        "base_price": Decimal("2650000"),
        "base_price_weekend": Decimal("2900000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "suite-2",
        "name": {"uz": "Lyuks ikki kishilik", "ru": "Люкс двухместный", "en": "Suite Double"},
        "capacity": 2,
        "base_price": Decimal("4850000"),
        "base_price_weekend": Decimal("5300000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
    {
        "key": "cottage-4",
        "name": {"uz": "Kottej to'rt kishilik", "ru": "Коттедж четырехместный", "en": "Cottage Quad"},
        "capacity": 4,
        "base_price": Decimal("6000000"),
        "base_price_weekend": Decimal("6500000"),
        "discount_percent": Decimal("20"),
        "base_currency": "UZS",
        "min_nights": 1,
    },
]

# ── extra bed configs ──────────────────────────────────────────────────────

EXTRA_BEDS = [
    {
        "name": {
            "uz": "Bolalar (4-10 yosh) — ovqat, qo'shimcha matras, to'shak anjomi",
            "ru": "Дети 4–10 лет — питание, доп. матрас, постельные принадлежности",
            "en": "Children 4–10 years — meals, extra mattress, bedding",
        },
        "price_per_night": Decimal("500000"),
        "currency": "UZS",
        "max_count": 4,
    },
    {
        "name": {
            "uz": "Bolalar (10 yoshdan katta) — ovqat, qo'shimcha matras, to'shak anjomi",
            "ru": "Дети старше 10 лет — питание, доп. матрас, постельные принадлежности",
            "en": "Children over 10 years — meals, extra mattress, bedding",
        },
        "price_per_night": Decimal("1000000"),
        "currency": "UZS",
        "max_count": 4,
    },
]

# ── amenities ──────────────────────────────────────────────────────────────
# Keyed dict so programs can reference amenities without string matching.

AMENITIES: dict[str, dict] = {
    # Nutrition
    "meal_4x":       {"name": {"uz": "4 mahal ovqatlanish",        "ru": "4-х разовое питание",                   "en": "4-Time Meals"},                          "category": "nutrition"},
    "phytobar":      {"name": {"uz": "Fito bar",                    "ru": "Фито бар",                              "en": "Phytobar"},                              "category": "nutrition"},
    # Facilities
    "pool":          {"name": {"uz": "Yopiq va ochiq basseyn",      "ru": "Крытый и Открытый бассейн",             "en": "Indoor & Outdoor Pool"},                 "category": "facility"},
    "playstation":   {"name": {"uz": "Play Station xonasi",         "ru": "Комната для игры Play Station",         "en": "PlayStation Room"},                      "category": "facility"},
    "bicycles":      {"name": {"uz": "Velosipedlar",                "ru": "Велосипеды на территории",              "en": "Bicycles on Premises"},                  "category": "facility"},
    "horse_therapy": {"name": {"uz": "Ippoterapiya",                "ru": "Иппотерапия (прогулки на лошадях)",     "en": "Horse Therapy"},                         "category": "facility"},
    "hair_salon":    {"name": {"uz": "Ayollar sartaroshxonasi",     "ru": "Парикмахерская для женщин",             "en": "Women's Hair Salon"},                    "category": "facility"},
    "animators":     {"name": {"uz": "Bolalar animatorlari",        "ru": "Аниматоры для детей",                   "en": "Children's Animators"},                  "category": "facility"},
    "babysitting":   {"name": {"uz": "Enaga xizmati (3 yoshdan)",   "ru": "Услуги няни для детей от 3-х лет",      "en": "Babysitting (from age 3)"},               "category": "facility"},
    "gym":           {"name": {"uz": "Trenajyor zali",              "ru": "Тренажёрный зал",                       "en": "Fitness Center"},                        "category": "facility"},
    "billiards":     {"name": {"uz": "Bilyard, stol tennisi",       "ru": "Бильярд, настольный теннис",            "en": "Billiards & Table Tennis"},              "category": "facility"},
    "sports_courts": {"name": {"uz": "Sport maydonlari",            "ru": "Футбол, баскетбол, волейбол, теннис",   "en": "Sports Courts"},                         "category": "facility"},
    "cinema":        {"name": {"uz": "Kinoteatr",                   "ru": "Кинотеатр (летний/зимний)",             "en": "Cinema (Summer/Winter)"},                "category": "facility"},
    "sauna":         {"name": {"uz": "Sauna",                       "ru": "Сауна",                                 "en": "Sauna"},                                 "category": "facility"},
    # Medical — program-level
    "massage_local": {"name": {"uz": "Davolash massaji (lokal)",    "ru": "Лечебный массаж (локально)",            "en": "Therapeutic Massage (Local)"},           "category": "medical"},
    "doctor_exam":   {"name": {"uz": "Shifokor ko'rigi va nazorat", "ru": "Осмотр и наблюдение врачей",            "en": "Doctor Examination & Monitoring"},        "category": "medical"},
    "lab_tests":     {"name": {"uz": "Laboratoriya tahlillari",     "ru": "Лабораторные анализы",                  "en": "Laboratory Tests"},                      "category": "medical"},
    "physiotherapy": {"name": {"uz": "Fizioterapiya muolajalari",   "ru": "Физиотерапевтические процедуры",        "en": "Physiotherapy Procedures"},              "category": "medical"},
    "hydrotherapy":  {"name": {"uz": "Gidroterapiya muolajalari",   "ru": "Гидротерапевтические процедуры",        "en": "Hydrotherapy Procedures"},               "category": "medical"},
    "ozonotherapy":  {"name": {"uz": "Ozonoterapiya",               "ru": "Озонотерапия",                          "en": "Ozonotherapy"},                          "category": "medical"},
    # Hydrotherapy specific
    "shower_circ":   {"name": {"uz": "Sirkular dush",               "ru": "Циркулярный душ",                       "en": "Circular Shower"},                       "category": "medical"},
    "shower_sharko": {"name": {"uz": "Sharko dushi",                "ru": "Душ Шарко",                             "en": "Charcot Shower"},                        "category": "medical"},
    "shower_casc":   {"name": {"uz": "Kaskad dushi",                "ru": "Каскадный душ",                         "en": "Cascade Shower"},                        "category": "medical"},
    "colon_hydro":   {"name": {"uz": "Gidrokolonterapiya",          "ru": "Гидроколонотерапия",                    "en": "Colon Hydrotherapy"},                    "category": "medical"},
    "hydro_bath":    {"name": {"uz": "Tibbiy gidromassaj vannasi",  "ru": "Медицинская гидромассажная ванна",       "en": "Medical Hydromassage Bath"},             "category": "medical"},
    "shower_vichy":  {"name": {"uz": "Vishi dushi",                 "ru": "Душ Виши",                              "en": "Vichy Shower"},                          "category": "medical"},
    "shower_asc":    {"name": {"uz": "Ko'tariluvchi dush",          "ru": "Восходящий душ",                        "en": "Ascending Shower"},                      "category": "medical"},
    "pearl_bath":    {"name": {"uz": "Marvarid vannasi",            "ru": "Жемчужные ванны",                       "en": "Pearl Bath"},                            "category": "medical"},
    "hand_bath":     {"name": {"uz": "Qo'l vannasi",                "ru": "Ручные ванны",                          "en": "Hand Bath"},                             "category": "medical"},
    "foot_bath":     {"name": {"uz": "Oyoq vannasi",                "ru": "Ножные ванны",                          "en": "Foot Bath"},                             "category": "medical"},
    # Physiotherapy specific
    "ecg":           {"name": {"uz": "EKG / Elektrokardiograf",     "ru": "ЭКГ / Электрокардиограф",              "en": "ECG / Electrocardiograph"},              "category": "medical"},
    "uhf":           {"name": {"uz": "UVCh-Ultraterm",              "ru": "УВЧ-Ультратерм",                        "en": "UHF Ultratherm"},                        "category": "medical"},
    "radiotherm":    {"name": {"uz": "Radioterm",                   "ru": "Радиотерм",                             "en": "Radiotherm"},                            "category": "medical"},
    "interference":  {"name": {"uz": "Interferentsoterapiya",       "ru": "Интерференцтерапия",                    "en": "Interference Therapy"},                  "category": "medical"},
    "stereodinator": {"name": {"uz": "Stereodinator",               "ru": "Стереодинатор",                         "en": "Stereodinator"},                         "category": "medical"},
    "neurotone":     {"name": {"uz": "Neyroton",                    "ru": "Нейротон",                              "en": "Neurotone"},                             "category": "medical"},
    "massage_table": {"name": {"uz": "Massaj kushetkasi",           "ru": "Массажная кушетка",                     "en": "Massage Table"},                         "category": "medical"},
    "laser":         {"name": {"uz": "Lazeroterapiya",              "ru": "Лазеротерапия",                         "en": "Laser Therapy"},                         "category": "medical"},
    "darsonval":     {"name": {"uz": "Darsonvalizatsiya",           "ru": "Дарсонвализация",                       "en": "Darsonvalization"},                      "category": "medical"},
    "hi_top":        {"name": {"uz": "Hi-Top",                      "ru": "Hi-Тор",                                "en": "Hi-Top"},                                "category": "medical"},
    "mechano":       {"name": {"uz": "Mekhanomassaj",               "ru": "Механомассаж",                          "en": "Mechano-massage"},                       "category": "medical"},
    "uv_tube":       {"name": {"uz": "UFO (tubus)",                 "ru": "УФО (тубус)",                           "en": "UV Irradiation (Tube)"},                 "category": "medical"},
    "inhalation":    {"name": {"uz": "Ingalyatsiya",                "ru": "Ингаляция",                             "en": "Inhalation Therapy"},                    "category": "medical"},
    "magneto":       {"name": {"uz": "Magnitoterapiya",             "ru": "Магнитотерапия",                        "en": "Magnetotherapy"},                        "category": "medical"},
    "infrared":      {"name": {"uz": "Infraruж",                    "ru": "Инфраруж",                              "en": "Infrared Therapy"},                      "category": "medical"},
    "phonophore":    {"name": {"uz": "Fonoforez",                   "ru": "Фонофорез",                             "en": "Phonophoresis"},                         "category": "medical"},
    "massage":       {"name": {"uz": "Massaj",                      "ru": "Массаж",                                "en": "Massage"},                               "category": "medical"},
    "lymph":         {"name": {"uz": "Limfodrenaj",                 "ru": "Лимфодренаж",                           "en": "Lymph Drainage"},                        "category": "medical"},
}

# Keys of amenities shown in the sanatorium catalog (visible to guests for filtering)
SANATORIUM_AMENITY_KEYS = [
    "meal_4x", "phytobar", "pool", "bicycles", "horse_therapy", "gym",
    "billiards", "sports_courts", "cinema", "sauna",
    "physiotherapy", "hydrotherapy", "ozonotherapy",
]

# ── treatment programs ─────────────────────────────────────────────────────
# Exactly mirrors the table columns: 1-4 / 5 / 7 / 10 nights

BASE_AMENITY_KEYS = [
    "meal_4x", "phytobar", "pool", "playstation", "bicycles",
    "horse_therapy", "hair_salon", "animators", "babysitting",
    "gym", "billiards", "sports_courts", "cinema", "massage_local",
]

PROGRAMS = [
    {
        "name": {
            "uz": "Standart (1-4 kun)",
            "ru": "Стандарт (1–4 суток)",
            "en": "Standard (1–4 nights)",
        },
        "min_nights": 1,
        "max_nights": 4,
        "amenity_keys": BASE_AMENITY_KEYS,
    },
    {
        "name": {
            "uz": "Sog'lomlashtirish (5 kun)",
            "ru": "Оздоровление (5 суток)",
            "en": "Wellness (5 nights)",
        },
        "min_nights": 5,
        "max_nights": 6,
        "amenity_keys": BASE_AMENITY_KEYS + ["doctor_exam", "lab_tests", "physiotherapy", "hydrotherapy"],
    },
    {
        "name": {
            "uz": "Davolash (7 kun)",
            "ru": "Лечение (7 суток)",
            "en": "Treatment (7 nights)",
        },
        "min_nights": 7,
        "max_nights": 9,
        "amenity_keys": BASE_AMENITY_KEYS + ["doctor_exam", "lab_tests", "physiotherapy", "hydrotherapy", "ozonotherapy"],
    },
    {
        "name": {
            "uz": "Intensiv davolash (10 kun)",
            "ru": "Интенсивное лечение (10 суток)",
            "en": "Intensive Treatment (10 nights)",
        },
        "min_nights": 10,
        "max_nights": None,
        "amenity_keys": BASE_AMENITY_KEYS + ["doctor_exam", "lab_tests", "physiotherapy", "hydrotherapy", "ozonotherapy", "sauna"],
    },
]


# ── helpers ────────────────────────────────────────────────────────────────

_amenity_cache: dict[str, Amenity] = {}


async def _load_amenity_cache(db) -> None:
    rows = (await db.execute(select(Amenity))).scalars().all()
    for row in rows:
        ru = row.name.get("ru") if isinstance(row.name, dict) else None
        if ru:
            _amenity_cache[ru] = row


async def get_or_create_amenity(db, key: str, data: dict) -> Amenity:
    ru_name = data["name"]["ru"]
    if ru_name in _amenity_cache:
        return _amenity_cache[ru_name]
    obj = Amenity(name=data["name"], category=data["category"])
    db.add(obj)
    await db.flush()
    _amenity_cache[ru_name] = obj
    print(f"  ✓ amenity: {ru_name}")
    return obj


async def main() -> None:
    async with SessionLocal() as db:

        # 1. Admin user
        admin = (await db.execute(select(User).where(User.email == ADMIN["email"]))).scalar_one_or_none()
        if admin is None:
            admin = User(
                email=ADMIN["email"],
                password_hash=hash_password(ADMIN["password"]),
                role=UserRole.ADMIN,
                full_name=ADMIN["full_name"],
                is_active=True,
            )
            db.add(admin)
            await db.flush()
            print(f"✓ admin: {ADMIN['email']}")
        else:
            print(f"- admin already exists: {ADMIN['email']}")

        # 2. Sanatorium
        san = (
            await db.execute(
                select(Sanatorium)
                .where(Sanatorium.slug == SANATORIUM["slug"])
                .options(selectinload(Sanatorium.amenities))
            )
        ).scalar_one_or_none()
        if san is None:
            san = Sanatorium(
                name=SANATORIUM["name"],
                slug=SANATORIUM["slug"],
                description=SANATORIUM["description"],
                city=SANATORIUM["city"],
                address=SANATORIUM["address"],
                lat=SANATORIUM["lat"],
                lng=SANATORIUM["lng"],
                phone=SANATORIUM["phone"],
                stars=SANATORIUM["stars"],
                treatment_focuses=SANATORIUM["treatment_focuses"],
                status=SanatoriumStatus.APPROVED,
                admin_user_id=admin.id,
            )
            db.add(san)
            await db.flush()
            # Load the amenities collection so we can append to it
            await db.refresh(san, ["amenities"])
            print(f"✓ sanatorium: {san.name}")
        else:
            print(f"- sanatorium already exists: {san.name}")

        # 3. All amenities
        print("\nAmenities:")
        await _load_amenity_cache(db)
        amenity_map: dict[str, Amenity] = {}
        for key, data in AMENITIES.items():
            amenity_map[key] = await get_or_create_amenity(db, key, data)

        # 4. Link facility amenities to sanatorium
        existing_san_amenity_ids = {a.id for a in san.amenities} if san.amenities else set()
        added = 0
        for key in SANATORIUM_AMENITY_KEYS:
            amenity = amenity_map[key]
            if amenity.id not in existing_san_amenity_ids:
                san.amenities.append(amenity)
                added += 1
        if added:
            await db.flush()
            print(f"\n✓ linked {added} facility amenities to sanatorium")
        else:
            print("\n- sanatorium amenities already linked")

        # 5. Room categories + availability
        print("\nRoom categories:")
        today = date.today()
        existing_rooms = (
            await db.execute(
                select(RoomCategory).where(RoomCategory.sanatorium_id == san.id)
            )
        ).scalars().all()
        existing_room_names_ru = {
            r.name.get("ru") for r in existing_rooms if isinstance(r.name, dict)
        }

        for tmpl in ROOMS:
            if tmpl["name"]["ru"] in existing_room_names_ru:
                print(f"  - {tmpl['name']['ru']}")
                continue

            room = RoomCategory(
                sanatorium_id=san.id,
                name=tmpl["name"],
                capacity=tmpl["capacity"],
                base_price=tmpl["base_price"],
                base_price_weekend=tmpl["base_price_weekend"],
                discount_percent=tmpl["discount_percent"],
                base_currency=tmpl["base_currency"],
                min_nights=tmpl["min_nights"],
                is_active=True,
            )
            db.add(room)
            await db.flush()

            # Availability: 120 days from today, 10 units each
            for offset in range(120):
                db.add(RoomAvailability(
                    room_category_id=room.id,
                    date=today + timedelta(days=offset),
                    units_total=10,
                    units_available=10,
                ))
            await db.flush()
            print(
                f"  ✓ {tmpl['name']['ru']} — "
                f"{tmpl['base_price']:,.0f} / {tmpl['base_price_weekend']:,.0f} UZS "
                f"(cap {tmpl['capacity']}, -20%)"
            )

        # 6. Extra bed configs
        print("\nExtra bed configs:")
        for bed in EXTRA_BEDS:
            ru_name = bed["name"]["ru"]
            existing = (
                await db.execute(
                    select(ExtraBedConfig).where(
                        ExtraBedConfig.sanatorium_id == san.id,
                        ExtraBedConfig.price_per_night == bed["price_per_night"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                print(f"  - {ru_name}")
                continue
            db.add(ExtraBedConfig(
                sanatorium_id=san.id,
                name=bed["name"],
                price_per_night=bed["price_per_night"],
                currency=bed["currency"],
                max_count=bed["max_count"],
                is_active=True,
            ))
            await db.flush()
            print(f"  ✓ {ru_name} — {bed['price_per_night']:,.0f} UZS/night")

        # 7. Treatment programs
        print("\nTreatment programs:")
        for prog in PROGRAMS:
            existing = (
                await db.execute(
                    select(TreatmentProgram).where(
                        TreatmentProgram.sanatorium_id == san.id,
                        TreatmentProgram.min_nights == prog["min_nights"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                print(f"  - {prog['name']['ru']}")
                continue

            program = TreatmentProgram(
                sanatorium_id=san.id,
                name=prog["name"],
                min_nights=prog["min_nights"],
                max_nights=prog["max_nights"],
                is_active=True,
            )
            for key in prog["amenity_keys"]:
                program.amenities.append(amenity_map[key])
            db.add(program)
            await db.flush()
            print(f"  ✓ {prog['name']['ru']} ({len(prog['amenity_keys'])} services)")

        await db.commit()
        print("\n✅ Done.")
        print(f"\nAdmin login: {ADMIN['email']} / {ADMIN['password']}")
        print(f"Sanatorium:  {SANATORIUM['name']} (slug: {SANATORIUM['slug']})")
        print(f"Rooms:       {len(ROOMS)} categories × 120 days availability")
        print(f"Programs:    {len(PROGRAMS)} treatment tiers")


if __name__ == "__main__":
    asyncio.run(main())
