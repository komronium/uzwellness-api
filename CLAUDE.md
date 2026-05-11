# UzWellness API — Claude Code Guide

## Loyiha haqida

**uzwellness.com** — O'zbekistondagi sanatoriyalar uchun bron qilish platformasi.  
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
| `admin` | Faqat o'z sanatoriyasi, xonalari, mavjudligi |
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
7. `final_price` snapshot (markup keyinchalik o'zgarsa ham bron narxi o'zgarmaydi)
8. `COMMIT`

## Narx hisoblash

```python
final_price = base_price * (1 + markup_percent / 100)
# Admin: base_price belgilaydi
# Super_admin: markup_percent belgilaydi (0–100%)
# Kurs: USD_UZS exchange_rates jadvalidan
```

## Ma'lumotlar bazasi

```
users → sanatoriums → room_categories → room_availability
                                      ↘ bookings → notifications
exchange_rates (alohida)
```

- `room_availability`: `UNIQUE(room_category_id, date)` — bir kunda bitta qator
- `bookings.final_price`: snapshot, `room_categories.base_price` ga bog'liq emas
- FK strategiya: `SET NULL` (user/room o'chsa, bron tarixi saqlanadi)

## Test infratuzilmasi

```python
# conftest.py da tayyor fixture'lar:
customer_headers, admin_headers, super_admin_headers
db  # har test uchun yangi session, keyin truncate
client  # ASGI test client, dependency override qilingan
```

```bash
# Test DB yaratish (bir marta)
python -c "
import asyncio, asyncpg
async def f():
    c = await asyncpg.connect('postgresql://sanotour:sanotour@localhost/sanotour')
    await c.execute('CREATE DATABASE sanotour_test')
asyncio.run(f())"
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
