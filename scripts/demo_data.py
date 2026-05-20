"""Populate the database with realistic demo data.

Idempotent: running multiple times is safe (checks existing data first).

Usage:
    uv run python -m scripts.demo_data
"""

import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus
from app.models.exchange_rate import ExchangeRate
from app.models.notification import Notification
from app.models.package import Package, PackageItem, PackageItemType
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.models.visa_request import VisaPurpose, VisaRequest, VisaStatus
from sqlalchemy import select

# ── constants ──────────────────────────────────────────────────────────────

SUPER_ADMIN_EMAIL = "admin@uzwellness.com"
SUPER_ADMIN_PASSWORD = "Admin123!"

ADMINS = [
    {"email": "charvak@uzwellness.com",   "password": "Admin123!", "full_name": "Charvak Admin"},
    {"email": "samarqand@uzwellness.com", "password": "Admin123!", "full_name": "Samarqand Admin"},
    {"email": "buxoro@uzwellness.com",    "password": "Admin123!", "full_name": "Buxoro Admin"},
    {"email": "namangan@uzwellness.com",  "password": "Admin123!", "full_name": "Namangan Admin"},
]

CUSTOMERS = [
    {"email": "ali@gmail.com",     "password": "User123!", "full_name": "Ali Karimov",    "phone": "+998901234567"},
    {"email": "zulfiya@gmail.com", "password": "User123!", "full_name": "Zulfiya Yusupova","phone": "+998907654321"},
    {"email": "jasur@gmail.com",   "password": "User123!", "full_name": "Jasur Toshmatov", "phone": "+998931112233"},
    {"email": "malika@gmail.com",  "password": "User123!", "full_name": "Malika Rahimova", "phone": "+998946667788"},
    {"email": "bobur@gmail.com",   "password": "User123!", "full_name": "Bobur Xasanov",   "phone": "+998991234567"},
    {"email": "nilufar@gmail.com", "password": "User123!", "full_name": "Nilufar Islomova","phone": "+998977778899"},
    {"email": "sardor@gmail.com",  "password": "User123!", "full_name": "Sardor Nazarov",  "phone": "+998901230000"},
    {"email": "dilnoza@gmail.com", "password": "User123!", "full_name": "Dilnoza Mirzayeva","phone": "+998909876543"},
]

SANATORIUMS = [
    {
        "name": {
            "uz": "Charvak Oromgohi",
            "ru": "Чарвак Оромгохи",
            "en": "Charvak Resort",
        },
        "slug": "charvak-oromgohi",
        "description": {
            "uz": "Charvak suv ombori yonida joylashgan zamonaviy dam olish maskani.",
            "ru": "Современный курорт на берегу Чарвакского водохранилища.",
            "en": "A modern resort located on the shores of Charvak Reservoir.",
        },
        "city": "Toshkent viloyati",
        "address": {
            "uz": "Charvak qo'rg'oni, Bostanliq tumani",
            "ru": "Чарвакский кишлак, Бостанлыкский район",
            "en": "Charvak village, Bostanlyk district",
        },
        "lat": Decimal("41.5500"),
        "lng": Decimal("70.0167"),
        "stars": 5,
    },
    {
        "name": {
            "uz": "Nur Samarqand",
            "ru": "Нур Самарканд",
            "en": "Nur Samarkand",
        },
        "slug": "nur-samarqand",
        "description": {
            "uz": "Samarqandning tarixiy markazida joylashgan, zamonaviy shifo markazi.",
            "ru": "Современный оздоровительный центр в историческом центре Самарканда.",
            "en": "A modern wellness centre in the heart of historic Samarkand.",
        },
        "city": "Samarqand",
        "address": {
            "uz": "Registon ko'chasi, 12",
            "ru": "ул. Регистан, 12",
            "en": "12 Registan Street",
        },
        "lat": Decimal("39.6542"),
        "lng": Decimal("66.9597"),
        "stars": 4,
    },
    {
        "name": {
            "uz": "Buxoro Ziloli",
            "ru": "Бухара Зилоли",
            "en": "Bukhara Ziloli",
        },
        "slug": "buxoro-ziloli",
        "description": {
            "uz": "Qadimiy Buxoro shahri yaqinida, toza havo va shifo manbalari bilan.",
            "ru": "Рядом с древней Бухарой, чистый воздух и природные источники.",
            "en": "Near ancient Bukhara, clean air and natural healing springs.",
        },
        "city": "Buxoro",
        "address": {
            "uz": "Olimlar ko'chasi, 5",
            "ru": "ул. Олимлар, 5",
            "en": "5 Olimlar Street",
        },
        "lat": Decimal("39.7747"),
        "lng": Decimal("64.4286"),
        "stars": 3,
    },
    {
        "name": {
            "uz": "Namangan Bog'i",
            "ru": "Наманган Боги",
            "en": "Namangan Garden",
        },
        "slug": "namangan-bogi",
        "description": {
            "uz": "Namangan shahridagi katta bog' ichida joylashgan tinch dam olish joyi.",
            "ru": "Тихий курорт в большом парке Намангана.",
            "en": "A peaceful resort nestled inside a large park in Namangan.",
        },
        "city": "Namangan",
        "address": {
            "uz": "Bog' ko'chasi, 88",
            "ru": "ул. Бог, 88",
            "en": "88 Bog Street",
        },
        "lat": Decimal("41.0011"),
        "lng": Decimal("71.6728"),
        "stars": 4,
    },
]

# room_categories per sanatorium index
ROOM_TEMPLATES = [
    [
        {"name": {"uz": "Standart xona", "ru": "Стандартный номер", "en": "Standard Room"},
         "capacity": 2, "base_price": Decimal("80.00"),  "base_currency": "USD", "min_nights": 1},
        {"name": {"uz": "Deluxe xona",   "ru": "Делюкс номер",      "en": "Deluxe Room"},
         "capacity": 2, "base_price": Decimal("120.00"), "base_currency": "USD", "min_nights": 2},
        {"name": {"uz": "Lyuks",         "ru": "Люкс",              "en": "Suite"},
         "capacity": 3, "base_price": Decimal("200.00"), "base_currency": "USD", "min_nights": 2},
        {"name": {"uz": "Prezident lyuks","ru": "Президентский люкс","en": "Presidential Suite"},
         "capacity": 4, "base_price": Decimal("350.00"), "base_currency": "USD", "min_nights": 3},
    ],
    [
        {"name": {"uz": "Iqtisodiy",  "ru": "Эконом",      "en": "Economy"},
         "capacity": 2, "base_price": Decimal("600000"), "base_currency": "UZS", "min_nights": 1},
        {"name": {"uz": "Standart",   "ru": "Стандарт",    "en": "Standard"},
         "capacity": 2, "base_price": Decimal("900000"), "base_currency": "UZS", "min_nights": 1},
        {"name": {"uz": "Oila xonasi","ru": "Семейный",    "en": "Family Room"},
         "capacity": 4, "base_price": Decimal("1400000"),"base_currency": "UZS", "min_nights": 2},
    ],
    [
        {"name": {"uz": "Standart",  "ru": "Стандарт",  "en": "Standard"},
         "capacity": 2, "base_price": Decimal("450000"), "base_currency": "UZS", "min_nights": 1},
        {"name": {"uz": "Komfort",   "ru": "Комфорт",   "en": "Comfort"},
         "capacity": 2, "base_price": Decimal("650000"), "base_currency": "UZS", "min_nights": 2},
        {"name": {"uz": "Oila",      "ru": "Семейный",  "en": "Family"},
         "capacity": 5, "base_price": Decimal("1000000"),"base_currency": "UZS", "min_nights": 2},
    ],
    [
        {"name": {"uz": "Standart",   "ru": "Стандарт",   "en": "Standard"},
         "capacity": 2, "base_price": Decimal("75.00"),  "base_currency": "USD", "min_nights": 1},
        {"name": {"uz": "Junior lyuks","ru": "Джуниор люкс","en": "Junior Suite"},
         "capacity": 2, "base_price": Decimal("130.00"), "base_currency": "USD", "min_nights": 2},
        {"name": {"uz": "VIP xona",   "ru": "VIP номер",  "en": "VIP Room"},
         "capacity": 3, "base_price": Decimal("180.00"), "base_currency": "USD", "min_nights": 2},
    ],
]

PACKAGE_TEMPLATES = [
    {
        "slug": "charvak-wellness-weekend",
        "sanatorium_slug": "charvak-oromgohi",
        "title": {
            "uz": "Charvak Wellness Weekend",
            "ru": "Велнес-уикенд в Чарваке",
            "en": "Charvak Wellness Weekend",
        },
        "description": {
            "uz": "3 kecha davomida tog' havosi, transfer, ovqatlanish va shifo muolajalari.",
            "ru": "3 ночи с горным воздухом, трансфером, питанием и оздоровительными процедурами.",
            "en": "3 nights with mountain air, transfer, meals, and wellness treatments.",
        },
        "duration_nights": 3,
        "base_price": Decimal("690.00"),
        "currency": "USD",
        "items": [
            {
                "item_type": PackageItemType.TRANSFER,
                "title": {
                    "uz": "Aeroportdan transfer",
                    "ru": "Трансфер из аэропорта",
                    "en": "Airport transfer",
                },
                "description": {
                    "uz": "Toshkent aeroportidan Charvakka borish va qaytish.",
                    "ru": "Трансфер из аэропорта Ташкента в Чарвак и обратно.",
                    "en": "Round-trip transfer from Tashkent airport to Charvak.",
                },
                "display_order": 1,
            },
            {
                "item_type": PackageItemType.HOTEL,
                "title": {
                    "uz": "3 kecha joylashuv",
                    "ru": "Проживание на 3 ночи",
                    "en": "3-night stay",
                },
                "description": {
                    "uz": "Standart yoki deluxe xona, mavjudlikka qarab.",
                    "ru": "Стандартный или делюкс номер при наличии.",
                    "en": "Standard or deluxe room, subject to availability.",
                },
                "display_order": 2,
            },
            {
                "item_type": PackageItemType.TREATMENT,
                "title": {
                    "uz": "Wellness muolajalari",
                    "ru": "Оздоровительные процедуры",
                    "en": "Wellness treatments",
                },
                "description": {
                    "uz": "Kundalik konsultatsiya va tiklanish dasturi.",
                    "ru": "Ежедневная консультация и восстановительная программа.",
                    "en": "Daily consultation and recovery program.",
                },
                "display_order": 3,
            },
        ],
    },
    {
        "slug": "samarqand-health-retreat",
        "sanatorium_slug": "nur-samarqand",
        "title": {
            "uz": "Samarqand Health Retreat",
            "ru": "Оздоровительный ретрит в Самарканде",
            "en": "Samarkand Health Retreat",
        },
        "description": {
            "uz": "5 kecha Samarqandda dam olish, tekshiruv va shaharga qisqa ekskursiya.",
            "ru": "5 ночей в Самарканде с отдыхом, обследованием и короткой экскурсией.",
            "en": "5 nights in Samarkand with rest, check-up, and a short city tour.",
        },
        "duration_nights": 5,
        "base_price": Decimal("990.00"),
        "currency": "USD",
        "items": [
            {
                "item_type": PackageItemType.HOTEL,
                "title": {
                    "uz": "5 kecha joylashuv",
                    "ru": "Проживание на 5 ночей",
                    "en": "5-night stay",
                },
                "description": {
                    "uz": "Nur Samarqand sanatoriysida ikki kishilik xona.",
                    "ru": "Двухместный номер в санатории Нур Самарканд.",
                    "en": "Double room at Nur Samarkand sanatorium.",
                },
                "display_order": 1,
            },
            {
                "item_type": PackageItemType.TREATMENT,
                "title": {
                    "uz": "Boshlang'ich tibbiy tekshiruv",
                    "ru": "Первичный медицинский осмотр",
                    "en": "Initial medical check-up",
                },
                "description": {
                    "uz": "Shifokor konsultatsiyasi va asosiy tavsiyalar.",
                    "ru": "Консультация врача и базовые рекомендации.",
                    "en": "Doctor consultation and baseline recommendations.",
                },
                "display_order": 2,
            },
            {
                "item_type": PackageItemType.EXCURSION,
                "title": {
                    "uz": "Registon ekskursiyasi",
                    "ru": "Экскурсия на Регистан",
                    "en": "Registan excursion",
                },
                "description": {
                    "uz": "Gid bilan yarim kunlik shaharga sayohat.",
                    "ru": "Полудневная экскурсия по городу с гидом.",
                    "en": "Half-day guided city tour.",
                },
                "display_order": 3,
            },
        ],
    },
    {
        "slug": "buxoro-recovery-tour",
        "sanatorium_slug": "buxoro-ziloli",
        "title": {
            "uz": "Buxoro Recovery Tour",
            "ru": "Восстановительный тур в Бухару",
            "en": "Bukhara Recovery Tour",
        },
        "description": {
            "uz": "7 kecha tiklanish dasturi, ovqatlanish va transport xizmati.",
            "ru": "7 ночей восстановительной программы с питанием и транспортом.",
            "en": "7-night recovery program with meals and transport.",
        },
        "duration_nights": 7,
        "base_price": Decimal("1250.00"),
        "currency": "USD",
        "items": [
            {
                "item_type": PackageItemType.MEAL,
                "title": {
                    "uz": "Kuniga 3 mahal ovqat",
                    "ru": "Трехразовое питание",
                    "en": "Three meals per day",
                },
                "description": {
                    "uz": "Diyetolog tavsiyasi bo'yicha menyu.",
                    "ru": "Меню по рекомендации диетолога.",
                    "en": "Menu based on dietitian recommendations.",
                },
                "display_order": 1,
            },
            {
                "item_type": PackageItemType.TREATMENT,
                "title": {
                    "uz": "7 kunlik tiklanish kursi",
                    "ru": "7-дневный курс восстановления",
                    "en": "7-day recovery course",
                },
                "description": {
                    "uz": "Mineral vannalar va yengil fizioterapiya.",
                    "ru": "Минеральные ванны и легкая физиотерапия.",
                    "en": "Mineral baths and light physiotherapy.",
                },
                "display_order": 2,
            },
            {
                "item_type": PackageItemType.TRANSFER,
                "title": {
                    "uz": "Temir yo'l vokzalidan transfer",
                    "ru": "Трансфер с железнодорожного вокзала",
                    "en": "Railway station transfer",
                },
                "description": {
                    "uz": "Buxoro vokzalidan sanatoriygacha kutib olish.",
                    "ru": "Встреча на вокзале Бухары и трансфер в санаторий.",
                    "en": "Pickup from Bukhara railway station to the sanatorium.",
                },
                "display_order": 3,
            },
        ],
    },
]

VISA_REQUEST_TEMPLATES = [
    {
        "user_email": "ali@gmail.com",
        "full_name": "Ali Karimov",
        "citizenship": "Kazakhstan",
        "passport_number": "KZ1234567",
        "date_of_birth": date(1991, 5, 14),
        "arrival_offset_days": 35,
        "stay_nights": 10,
        "purpose": VisaPurpose.TREATMENT,
        "status": VisaStatus.PENDING,
        "admin_notes": None,
    },
    {
        "user_email": "zulfiya@gmail.com",
        "full_name": "Zulfiya Yusupova",
        "citizenship": "Kyrgyzstan",
        "passport_number": "KG7654321",
        "date_of_birth": date(1988, 11, 3),
        "arrival_offset_days": 50,
        "stay_nights": 8,
        "purpose": VisaPurpose.TOURISM,
        "status": VisaStatus.PROCESSING,
        "admin_notes": "Passport scan received; invitation letter in progress.",
    },
    {
        "user_email": "jasur@gmail.com",
        "full_name": "Jasur Toshmatov",
        "citizenship": "Tajikistan",
        "passport_number": "TJ9988776",
        "date_of_birth": date(1985, 2, 22),
        "arrival_offset_days": 70,
        "stay_nights": 14,
        "purpose": VisaPurpose.TREATMENT,
        "status": VisaStatus.ISSUED,
        "admin_notes": "Demo visa issued for testing.",
    },
]


# ── helpers ────────────────────────────────────────────────────────────────

async def get_or_create_user(db, *, email, password, role, full_name, phone=None):
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing, False
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        full_name=full_name,
        phone=phone,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user, True


async def get_or_create_sanatorium(db, data, admin_id):
    existing = (
        await db.execute(select(Sanatorium).where(Sanatorium.slug == data["slug"]))
    ).scalar_one_or_none()
    if existing:
        return existing, False
    san = Sanatorium(
        name=data["name"],
        slug=data["slug"],
        description=data["description"],
        city=data["city"],
        address=data["address"],
        lat=data.get("lat"),
        lng=data.get("lng"),
        stars=data["stars"],
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_id,
    )
    db.add(san)
    await db.flush()
    return san, True


async def ensure_package_items(db, package: Package, item_templates):
    existing_items = (
        await db.execute(
            select(PackageItem).where(PackageItem.package_id == package.id)
        )
    ).scalars().all()
    existing_keys = {
        (item.item_type, item.display_order)
        for item in existing_items
    }
    created_count = 0
    for item_data in item_templates:
        key = (item_data["item_type"], item_data["display_order"])
        if key in existing_keys:
            continue
        db.add(PackageItem(
            package_id=package.id,
            item_type=item_data["item_type"],
            title=item_data["title"],
            description=item_data["description"],
            is_included=item_data.get("is_included", True),
            extra_price=item_data.get("extra_price"),
            display_order=item_data["display_order"],
        ))
        created_count += 1
    if created_count:
        await db.flush()
    return created_count


async def get_or_create_package(db, data, sanatorium_by_slug):
    existing = (
        await db.execute(select(Package).where(Package.slug == data["slug"]))
    ).scalar_one_or_none()
    if existing:
        created_items = await ensure_package_items(db, existing, data["items"])
        return existing, False, created_items

    sanatorium = sanatorium_by_slug.get(data["sanatorium_slug"])
    package = Package(
        slug=data["slug"],
        title=data["title"],
        description=data["description"],
        duration_nights=data["duration_nights"],
        base_price=data["base_price"],
        currency=data["currency"],
        sanatorium_id=sanatorium.id if sanatorium is not None else None,
        is_active=True,
    )
    db.add(package)
    await db.flush()
    created_items = await ensure_package_items(db, package, data["items"])
    return package, True, created_items


async def get_or_create_visa_request(db, data, customer_by_email, today):
    existing = (
        await db.execute(
            select(VisaRequest).where(
                VisaRequest.passport_number == data["passport_number"]
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False

    customer = customer_by_email.get(data["user_email"])
    arrival_date = today + timedelta(days=data["arrival_offset_days"])
    visa = VisaRequest(
        user_id=customer.id if customer is not None else None,
        full_name=data["full_name"],
        citizenship=data["citizenship"],
        passport_number=data["passport_number"],
        date_of_birth=data["date_of_birth"],
        arrival_date=arrival_date,
        departure_date=arrival_date + timedelta(days=data["stay_nights"]),
        purpose=data["purpose"],
        status=data["status"],
        admin_notes=data["admin_notes"],
        contact_email=customer.email if customer is not None else None,
        contact_phone=customer.phone if customer is not None else None,
    )
    db.add(visa)
    await db.flush()
    return visa, True


# ── main seed ──────────────────────────────────────────────────────────────

async def main() -> None:
    async with SessionLocal() as db:

        # 1. Exchange rate
        rate_row = (
            await db.execute(select(ExchangeRate).where(ExchangeRate.pair == "USD_UZS"))
        ).scalar_one_or_none()
        if rate_row is None:
            db.add(ExchangeRate(
                pair="USD_UZS",
                rate=Decimal("12800.000000"),
                valid_from=datetime.now(tz=timezone.utc),
            ))
            print("✓ Exchange rate USD_UZS = 12800")
        else:
            print("- Exchange rate already exists")

        # 2. Super admin
        super_admin, created = await get_or_create_user(
            db, email=SUPER_ADMIN_EMAIL, password=SUPER_ADMIN_PASSWORD,
            role=UserRole.SUPER_ADMIN, full_name="Super Admin",
        )
        print(f"{'✓' if created else '-'} super_admin: {SUPER_ADMIN_EMAIL}")

        # 3. Admins
        admin_users = []
        for a in ADMINS:
            user, created = await get_or_create_user(
                db, email=a["email"], password=a["password"],
                role=UserRole.ADMIN, full_name=a["full_name"],
            )
            admin_users.append(user)
            print(f"{'✓' if created else '-'} admin: {a['email']}")

        # 4. Customers
        customer_users = []
        for c in CUSTOMERS:
            user, created = await get_or_create_user(
                db, email=c["email"], password=c["password"],
                role=UserRole.CUSTOMER, full_name=c["full_name"], phone=c["phone"],
            )
            customer_users.append(user)
            print(f"{'✓' if created else '-'} customer: {c['email']}")

        await db.flush()

        # 5. Sanatoriums + rooms + availability
        today = date.today()
        all_rooms: list[Room] = []

        for i, san_data in enumerate(SANATORIUMS):
            san, san_created = await get_or_create_sanatorium(db, san_data, admin_users[i].id)
            print(f"{'✓' if san_created else '-'} sanatorium: {san_data['name']['uz']}")

            for tmpl in ROOM_TEMPLATES[i]:
                existing_room = (
                    await db.execute(
                        select(Room).where(
                            Room.sanatorium_id == san.id,
                            Room.base_price == tmpl["base_price"],
                        )
                    )
                ).scalar_one_or_none()

                if existing_room:
                    all_rooms.append(existing_room)
                    continue

                markup = Decimal(str(random.choice([0, 5, 10, 15])))
                inventory = random.randint(3, 8)
                room = Room(
                    sanatorium_id=san.id,
                    name=tmpl["name"],
                    capacity=tmpl["capacity"],
                    inventory_count=inventory,
                    base_price=tmpl["base_price"],
                    base_currency=tmpl["base_currency"],
                    markup_percent=markup,
                    min_nights=tmpl["min_nights"],
                    is_active=True,
                )
                db.add(room)
                await db.flush()
                all_rooms.append(room)
                print(
                    f"  ✓ room: {tmpl['name']['en']} "
                    f"({tmpl['base_price']} {tmpl['base_currency']}, "
                    f"{inventory} units)"
                )

        await db.flush()

        # 6. Demo packages
        sanatorium_by_slug = {
            san.slug: san
            for san in (
                await db.execute(select(Sanatorium))
            ).scalars().all()
        }
        print("\nCreating demo packages...")
        for package_data in PACKAGE_TEMPLATES:
            package, created, created_items = await get_or_create_package(
                db, package_data, sanatorium_by_slug
            )
            prefix = "✓" if created else "-"
            item_msg = (
                f", {created_items} item(s) added"
                if created_items and not created
                else ""
            )
            print(f"{prefix} package: {package.title['en']}{item_msg}")

        # 7. Demo visa requests
        customer_by_email = {customer.email: customer for customer in customer_users}
        print("\nCreating demo visa requests...")
        for visa_data in VISA_REQUEST_TEMPLATES:
            visa, created = await get_or_create_visa_request(
                db, visa_data, customer_by_email, today
            )
            print(f"{'✓' if created else '-'} visa request: {visa.full_name}")

        # 8. Sample bookings (only if none exist yet)
        existing_bookings = (
            await db.execute(select(Booking).limit(1))
        ).scalar_one_or_none()

        if existing_bookings is None and all_rooms:
            print("\nCreating sample bookings...")
            for customer in random.sample(customer_users, k=min(5, len(customer_users))):
                room = random.choice(all_rooms)
                # pick a future date window (5–40 days from today)
                start_offset = random.randint(5, 40)
                nights = random.randint(room.min_nights, room.min_nights + 3)
                check_in = today + timedelta(days=start_offset)
                check_out = check_in + timedelta(days=nights)

                # lazy availability: get-or-create rows and bump units_booked
                existing_rows = {
                    row.date: row
                    for row in (
                        await db.execute(
                            select(RoomAvailability).where(
                                RoomAvailability.room_id == room.id,
                                RoomAvailability.date >= check_in,
                                RoomAvailability.date < check_out,
                            )
                        )
                    ).scalars().all()
                }
                full = False
                for offset_d in range(nights):
                    d = check_in + timedelta(days=offset_d)
                    row = existing_rows.get(d)
                    if row is None:
                        existing_rows[d] = RoomAvailability(
                            room_id=room.id,
                            date=d,
                            units_blocked=0,
                            units_booked=1,
                        )
                        db.add(existing_rows[d])
                    else:
                        if (
                            row.units_blocked + row.units_booked + 1
                            > room.inventory_count
                        ):
                            full = True
                            break
                        row.units_booked += 1
                if full:
                    continue

                from app.core.pricing import calculate_final_price
                final_price = calculate_final_price(room.base_price, room.markup_percent)

                booking = Booking(
                    user_id=customer.id,
                    room_id=room.id,
                    check_in=check_in,
                    check_out=check_out,
                    guests=random.randint(1, room.capacity),
                    status=BookingStatus.CONFIRMED,
                    final_price=final_price,
                    currency=room.base_currency,
                )
                db.add(booking)
                await db.flush()

                db.add(Notification(
                    booking_id=booking.id,
                    type="booking_created",
                    channel="email",
                    status="pending",
                ))
                print(
                    f"  ✓ booking: {customer.full_name} → "
                    f"{room.name.get('en', '?')} "
                    f"({check_in} – {check_out})"
                )

        await db.commit()
        print("\nDone.")
        print("\nAPI:        https://api.uzwellness.com/docs")
        print(f"super_admin: {SUPER_ADMIN_EMAIL} / {SUPER_ADMIN_PASSWORD}")
        print( "customer:    ali@gmail.com / User123!")


if __name__ == "__main__":
    asyncio.run(main())
