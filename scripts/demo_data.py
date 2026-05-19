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
from app.models.notification import Notification
from app.models.room import ExchangeRate, Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
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
        "address": "Charvak qo'rg'oni, Bostanliq tumani",
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
        "address": "Registon ko'chasi, 12",
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
        "address": "Olimlar ko'chasi, 5",
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
        "address": "Bog' ko'chasi, 88",
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

        # 6. Sample bookings (only if none exist yet)
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
