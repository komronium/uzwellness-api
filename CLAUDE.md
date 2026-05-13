# UzWellness API — Claude Code Guide

## Loyiha haqida

**uzwellness.com** — O'zbekistondagi sanatoriyalar uchun bron qilish platformasi (xalqaro mehmonlar uchun).  
Backend API: `api.uzwellness.com` | FastAPI + SQLAlchemy (async) + PostgreSQL

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

## Bron yaratish — atomik tranzaksiya

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
10. `COMMIT`

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

## Ma'lumotlar bazasi

```
users → sanatoriums ──────────────────────────────── sanatorium_images
              │
              ├─→ room_categories ──→ room_availability
              │         └──────────→ bookings ──→ notifications
              │                           └──→ booking_extra_beds
              │
              ├─→ extra_bed_configs          (qo'shimcha o'rin turlari: bolalar, qo'shimcha karavot)
              │
              └─→ treatment_programs ←──→ amenities   (program_amenities M2M)

exchange_rates (alohida)
```

### Jadvallar xususiyatlari

| Jadval | Muhim maydonlar |
|---|---|
| `room_categories` | `base_price` (weekday), `base_price_weekend` (null=weekday bilan bir xil), `discount_percent` (null=chegirma yo'q), `markup_percent` |
| `room_availability` | `UNIQUE(room_category_id, date)` — bir kunda bitta qator |
| `bookings.final_price` | TOTAL stay narxi snapshot (markup/chegirma freeze) |
| `booking_extra_beds` | `name_snapshot`, `price_per_night_snapshot` — freeze qilingan |
| `extra_bed_configs` | Sanatoriya adminsi belgilaydi (masalan "Bolalar 4-10 yosh: 500k/kun") |
| `amenities` | Global katalog (super_admin boshqaradi), `category` field bor |
| `treatment_programs` | `min_nights` + `max_nights` — qolish muddatiga qarab xizmatlar paketi |
| FK strategiya | `SET NULL` — user/room o'chsa, bron tarixi saqlanadi |

## Endpoint'lar xaritasi

```
# Xonalar
GET/POST  /rooms                      sanatoriumga xona qo'shish/ko'rish
GET       /rooms/search               mavjud xonalar qidirish
GET/PATCH /rooms/{id}                 xona ma'lumotlari
GET/POST  /rooms/{id}/availability    mavjudlik ko'rish/bulk yaratish

# Bronlash
POST      /bookings                   bron yaratish (extra_beds qo'shish mumkin)
GET       /bookings                   bronlar ro'yxati (RBAC)
PATCH     /bookings/{id}/cancel       bekor qilish

# Amenitlar (global katalog — super_admin)
GET/POST  /amenities
GET/PATCH/DELETE  /amenities/{id}

# Davolash dasturlari (admin — o'z sanatoriyasi uchun)
GET/POST  /programs?sanatorium_id=X
GET/PATCH/DELETE  /programs/{id}

# Qo'shimcha o'rinlar (admin — o'z sanatoriyasi uchun)
GET/POST  /extra-beds?sanatorium_id=X
GET/PATCH/DELETE  /extra-beds/{id}

# Sanatoriyalar
GET/POST  /sanatoriums
GET/PATCH /sanatoriums/{slug}
POST      /sanatoriums/{id}/approve   (super_admin)
POST      /sanatoriums/{id}/images    rasm yuklash
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
