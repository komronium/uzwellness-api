# UzWellness API — Claude Code Guide

## Loyiha haqida

**uzwellness.com** — O'zbekistondagi sanatoriya va wellness markazlari uchun bron qilish platformasi (xalqaro mehmonlar uchun).
Backend API: `api.uzwellness.com` | FastAPI + SQLAlchemy (async) + PostgreSQL

Bitta data modelda 2 ta mahsulot turi:
- **Sanatorium** — tibbiy kurort, sotiladigan birlik = **xona-tun** (+ ixtiyoriy bundled treatment program)
- **Wellness markaz** — yoga studio, spa, meditatsiya, detoks; sotiladigan birlik = **program/session** (drop-in class, weekend retreat) o'z narxi bilan

## Tez ishga tushirish

```bash
# Dev server (port 8000 band, shuning uchun 8080)
uv run fastapi dev app/main.py --port 8080

# Migratsiya
uv run alembic revision --autogenerate -m "tavsif"
uv run alembic upgrade head

# Testlar
uv run pytest
uv run pytest tests/test_booking_flow.py -v   # faqat bitta fayl

# Demo ma'lumotlar (idempotent)
uv run python -m scripts.demo_data

# Production super_admin ni seed qilish
uv run python -m scripts.seed
```

> **Muhim:** Lokal Postgres o'rnatilmagan. Testdan/migratsiyadan oldin Docker orqali ishga tushir:
> ```bash
> docker run -d --name uzwellness-pg \
>   -e POSTGRES_USER=sanotour -e POSTGRES_PASSWORD=sanotour \
>   -e POSTGRES_DB=sanotour -p 5432:5432 postgres:16-alpine
> # ~5 soniya kutib test DB yaratish:
> docker exec uzwellness-pg psql -U sanotour -c "CREATE DATABASE sanotour_test;"
> # Keyingi safar: docker start uzwellness-pg
> ```

## Arxitektura

```
HTTP → Router (yupqa) → Service (biznes mantiq) → ORM Model → PostgreSQL
```

- **Routers** (`app/api/v1/routers/`) — faqat HTTP: parametrlarni qabul qilish, javob qaytarish
- **Services** (`app/services/`) — barcha biznes mantiq shu yerda
- **Models** (`app/models/`) — SQLAlchemy ORM, jadval strukturasi
- **Schemas** (`app/schemas/`) — Pydantic: HTTP kirish/chiqish validatsiyasi

## RBAC — Rollar

| Rol | Huquq |
|---|---|
| `super_admin` | Hamma narsani boshqaradi, markup belgilaydi, sanatoriyani tasdiqlaydi |
| `admin` | Faqat o'z sanatoriyasi, xonalari, mavjudligi, dasturlar, qo'shimcha o'rinlar |
| `agent` | Faqat o'z bronlarini ko'radi |
| `customer` | Qidiradi, bron qiladi, o'zini bekor qiladi |

```python
# Router da ishlatish
require_super_admin = require_roles(UserRole.SUPER_ADMIN)
dependencies=[Depends(require_super_admin)]
```

## Muhim patterns

### Service yaratish
```python
class XyzService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

def get_xyz_service(db: AsyncSession = Depends(get_db)) -> XyzService:
    return XyzService(db)
```

### Commit pattern
```python
self.db.add(obj)
await self.db.commit()
await self.db.refresh(obj)
return obj
```

### Pydantic Read schema
```python
class XyzRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ...
```

### Paginated list response
```python
class XyzList(BaseModel):
    items: list[XyzRead]
    total: int
    limit: int
    offset: int
```

## Bron yaratish

`POST /bookings` ikki shaklni qabul qiladi — `room_category_id` **yoki** `program_id` (bittasi majburiy, ikkalovi birdaniga emas). `BookingCreate` schemasidagi `model_validator` buni majburlaydi.

### Room booking — atomik tranzaksiya

`booking_service.py::create()` ichida:
1. `SELECT room FOR UPDATE` — xona qatorini lock
2. Sanatoriya `approved` ekanligini tekshir
3. `min_nights`, `capacity` tekshir
4. `SELECT availability WHERE date IN (...) FOR UPDATE` — barcha kun qatorlarini lock
5. Har kunda `units_available >= 1` tekshir
6. `units_available -= 1` har kunda
7. `calculate_stay_total()` — har kunning narxini yig'ish (Juma/Shanba = weekend narx)
8. Extra o'rinlarni tekshir va narxga qo'sh
9. `final_price` snapshot (markup/chegirma keyinchalik o'zgarsa ham bron narxi o'zgarmaydi)
10. `booking_type = ROOM`, `COMMIT`

### Session booking

`booking_service.py::_create_session()` ichida:
1. `SELECT program` — `is_active` va `price`+`currency` to'ldirilgan bo'lishi shart
2. Sanatoriya `approved` ekanligini tekshir
3. `group_size_max` belgilangan bo'lsa, `guests <= group_size_max`
4. `check_out = check_out or check_in` (single-day session uchun OK)
5. `final_price = program.price × guests` (snapshot)
6. `booking_type = SESSION`, room_category_id = NULL, `COMMIT`

Cancel: room booking sanalardagi `units_available` ni qaytaradi; session booking faqat statusni `cancelled` qiladi.

## Narx hisoblash

```python
# Weekday narxi (Yak-Pay): base_price * (1 + markup/100) * (1 - discount/100)
# Weekend narxi (Jum-Shan): base_price_weekend * (1 + markup/100) * (1 - discount/100)
# Booking final_price = har kunning narxi yig'indisi (TOTAL, per-night emas)

# app/core/pricing.py:
calculate_night_price(base_price, base_price_weekend, markup_percent, discount_percent, is_weekend)
calculate_stay_total(room, dates)   # dates ro'yxatidan weekday/weekend hisoblab yig'adi
enrich_room(room, rate)             # → final_price, final_price_weekend, UZS/USD konversiyalar
```

| Kim | Nima |
|---|---|
| Admin | `base_price` (weekday), `base_price_weekend`, `discount_percent` belgilaydi |
| Super_admin | `markup_percent` belgilaydi (0–100%) |
| Kurs | `USD_UZS` — `exchange_rates` jadvalidan |

## i18n — uz / ru / en

Tarjima qilinadigan matnlar JSONB ustunda `{uz, ru, en}` shaklida saqlanadi.
Tegishli ustunlar: `sanatoriums.name|description|address|house_rules|cancellation_policy`,
`room_categories.name|description`, `treatment_programs.name|description|instructor_bio|what_to_bring`,
`amenities.name|description`, `extra_bed_configs.name|description`.

### Kirish (POST)

`TranslationsCreate` (`app/schemas/common.py`) — uchchala locale ham majburiy:
```json
{ "name": { "uz": "Vodiy", "ru": "Долина", "en": "Valley" } }
```
PATCH'lar `Translations` (qisman) qabul qiladi va `merge_translation_fields()`
orqali mavjud JSONB ustiga qo'shadi (yuborilmagan locale o'zgarmaydi).
`{ru: null}` yuborish — shu locale'ni butunlay olib tashlaydi.

### Chiqish (GET)

Dual-Read pattern (`XxxRead` vs `XxxAdminRead`):

| So'rov | Shakl | Mas'ul model |
|---|---|---|
| `GET /...` (default) | `name: str` (resolved) | `XxxRead.from_obj(obj, locale)` |
| `GET /...?include_translations=true` | `name: {uz,ru,en}` | `XxxAdminRead.model_validate(obj)` |
| `POST` / `PATCH` / `approve` / `reject` | `name: {uz,ru,en}` | `XxxAdminRead` (har doim) |

Yozish endpoint'lari doim AdminRead qaytaradi — admin nima saqlangani har 3 tilda
ko'rishi kerak. Public GET strings qaytaradi — frontend `pick` qilib o'tirmaydi.

### Locale resolution

`get_locale` dependency (`app/api/deps.py`) request locale'ini tanlaydi:
1. `?lang=uz|ru|en` query parametri
2. `Accept-Language` header (`fr-FR,ru;q=0.9,en;q=0.8` → `ru`; q-values e'tiborga
   olinmaydi, faqat ko'rsatilgan tartib)
3. Default: `en`

`pick_locale(translations, locale)` (`app/core/utils.py`) — so'ralgan locale yo'q
bo'lsa, `uz → ru → en → birinchi non-empty` fallback qiladi.

### Search / sort

- `?q=...` — `GET /sanatoriums` har 3 locale bo'yicha OR qidiradi
  (`coalesce` emas, `OR` — ko'p locale'larda match topish uchun).
- `?sort=name` — `coalesce(name->>locale, name->>uz, name->>ru, name->>en)` —
  request locale'iga qarab tartib o'zgaradi.

### Yangi i18n ustun qo'shganda

1. Model'da JSONB column: `description: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")`
2. Schema'da Create — `TranslationsCreate`, Update — `Translations | None`
3. `XxxRead`'da `description: str` + `from_obj` ichida `pick_locale(...)`
4. `XxxAdminRead`'da `description: dict`
5. Service create — `payload.description.model_dump()`
6. Service update — `merge_translation_fields(obj, data, (..., "description"))`
7. Alembic migration

## Ma'lumotlar bazasi

```
users → sanatoriums ──────────────────────────────── sanatorium_images
              │       (property_type: sanatorium | wellness)
              │       (wellness_category: spa_resort | yoga_retreat | ...)
              │
              ├─→ room_categories ──→ room_availability
              │         │           ──→ room_price_periods (mavsumiy)
              │         └──────────→ bookings ──→ notifications
              │                           └──→ booking_extra_beds
              │
              ├─→ extra_bed_configs          (qo'shimcha o'rin: bolalar, karavot)
              │
              ├─→ treatment_programs ←──→ amenities  (program_amenities M2M)
              │         │  (price+currency yoki min_nights — ikki "ko'rinish")
              │         └────→ bookings (booking_type='session')
              │
              └─→ sanatorium_reviews

exchange_rates (alohida)
```

### Property turlari

`sanatoriums` jadvalining bitta yozuvi `property_type` orqali ajratiladi:

| Maydon | SANATORIUM | WELLNESS |
|---|---|---|
| `property_type` | `sanatorium` | `wellness` |
| `wellness_category` | `null` | `spa_resort` / `yoga_retreat` / `meditation_center` / `fitness_resort` / `beauty_spa` / `digital_detox` |
| Asosiy inventar | `RoomCategory` (xona-tun) | `TreatmentProgram` (narx bilan) |
| Listing filtri | `region`, `treatment_focus`, `min_rating` | `wellness_category`, `city`, `min_rating` |
| Booking turi | `room` (availability lock) | `session` (`program.price × guests`) |

### Jadvallar xususiyatlari

| Jadval | Muhim maydonlar |
|---|---|
| `sanatoriums` | `property_type`, `wellness_category` (nullable), `region` (nullable), `weekly_schedule` JSONB, `cancellation_policy` JSONB, `house_rules` JSONB |
| `room_categories` | `base_price` (weekday), `base_price_weekend` (null=weekday bilan bir xil), `discount_percent` (null=chegirma yo'q), `markup_percent` |
| `room_availability` | `UNIQUE(room_category_id, date)` — bir kunda bitta qator |
| `room_price_periods` | Mavsumiy narx (date_from–date_to inclusive); shu oraliqdagi sanalar uchun room defaultlari override qilinadi |
| `bookings` | `booking_type` (`room` yoki `session`), `room_category_id` XOR `program_id`, `final_price` snapshot |
| `booking_extra_beds` | `name_snapshot`, `price_per_night_snapshot` — freeze qilingan |
| `extra_bed_configs` | Sanatoriya adminsi belgilaydi (masalan "Bolalar 4-10 yosh: 500k/kun") |
| `amenities` | Global katalog (super_admin boshqaradi), `category`: `facility`/`medical`/`nutrition`/`wellness` |
| `treatment_programs` | Ikki "shakl": **bundled** (`min_nights`+`max_nights`, narx yo'q — xona narxiga kiradi) yoki **standalone** (`price`+`currency`, ixtiyoriy `duration_minutes`, `instructor_name`, `instructor_bio`, `group_size_min/max`, `what_to_bring`) |
| FK strategiya | `SET NULL` — user/room/program o'chsa, bron tarixi saqlanadi |

## Endpoint'lar xaritasi

```
# Sanatoriumlar + Wellness markazlari (bitta endpoint, property_type filter bilan)
GET       /sanatoriums                ?property_type=sanatorium yoki wellness
                                      filterlar: city, region, wellness_category,
                                      stars, min_rating, amenity_ids,
                                      treatment_focus, q, sort, limit, offset
GET/POST  /sanatoriums                ko'rish / yaratish
GET/PATCH /sanatoriums/{id}           detail / yangilash
POST      /sanatoriums/{id}/approve   (super_admin)
POST      /sanatoriums/{id}/images    rasm yuklash

# Xonalar (faqat property_type=sanatorium uchun ma'noli)
GET/POST  /rooms                      sanatoriumga xona qo'shish/ko'rish
GET       /rooms/search               mavjud xonalar qidirish
GET/PATCH /rooms/{id}                 xona ma'lumotlari
GET/POST  /rooms/{id}/availability    mavjudlik ko'rish/bulk yaratish

# Programlar (sanatoriya bundle YOKI wellness session — narx bilan)
GET/POST  /programs?sanatorium_id=X
GET/PATCH/DELETE  /programs/{id}

# Bronlash (room va session)
POST      /bookings                   { room_category_id | program_id, ... }
GET       /bookings                   bronlar ro'yxati (RBAC)
PATCH     /bookings/{id}/cancel       bekor qilish

# Amenitlar (global katalog — super_admin)
GET/POST  /amenities
GET/PATCH/DELETE  /amenities/{id}

# Qo'shimcha o'rinlar (admin — o'z sanatoriyasi uchun)
GET/POST  /extra-beds?sanatorium_id=X
GET/PATCH/DELETE  /extra-beds/{id}

# Reviews
GET/POST  /sanatoriums/{id}/reviews
PATCH/DELETE  /reviews/{id}
```

## Test infratuzilmasi

```python
# conftest.py da tayyor fixture'lar:
customer_headers, admin_headers, super_admin_headers
db  # har test uchun yangi session, keyin truncate
client  # ASGI test client, dependency override qilingan
```

## Fayl qo'shish tartibi

Yangi entity uchun (masalan `Payment`):
1. `app/models/payment.py` — ORM model
2. `app/models/__init__.py` — export qo'sh
3. `app/schemas/payment.py` — Pydantic schemas
4. `app/services/payment_service.py` — biznes mantiq
5. `app/api/v1/routers/payments.py` — HTTP endpoints
6. `app/api/v1/__init__.py` — router ni include qil
7. `uv run alembic revision --autogenerate -m "create payments table"`

## Env sozlamalar

```env
DATABASE_URL=postgresql+asyncpg://sanotour:sanotour@localhost:5432/sanotour
TEST_DATABASE_URL=postgresql+asyncpg://sanotour:sanotour@localhost:5432/sanotour_test
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=...
CORS_ORIGINS=["http://localhost:3000","https://uzwellness.com","https://www.uzwellness.com"]
```

## Demo login'lar

```
super_admin: admin@uzwellness.com / Admin123!
admin:       charvak@uzwellness.com / Admin123!
customer:    ali@gmail.com / User123!
```

API docs: `http://localhost:8080/docs`

## Deploy (VPS — shared postgres/redis)

VPS da postgres va redis allaqachon ishlaydi, faqat app konteyner kerak.

```bash
# 1. Serverga kirish va reponi olish
git clone https://github.com/komronium/uzwellness-api /srv/uzwellness-api
cd /srv/uzwellness-api
cp .env.example .env   # kerakli qiymatlarni to'ldir

# 2. App konteyner ishga tushirish
docker compose -f docker-compose.prod.yml up -d --build

# 3. Nginx config joylashtirish
sudo cp deploy/nginx.conf /etc/nginx/sites-available/uzwellness-api
sudo ln -s /etc/nginx/sites-available/uzwellness-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 4. SSL (certbot)
sudo certbot --nginx -d api.uzwellness.com

# Yangilash
git pull && docker compose -f docker-compose.prod.yml up -d --build

# Loglar
docker logs uzwellness-api -f
```

**network_mode: host** ishlatiladi — konteyner host'dagi `localhost:5432` (postgres) va
`localhost:6379` (redis) ga to'g'ridan ulanadi. `.env` dagi `DATABASE_URL` da
`localhost` bo'lishi kerak (Docker service nomi emas).

App `127.0.0.1:8001` da tinglaydi → nginx `api.uzwellness.com` dan proxy qiladi.
