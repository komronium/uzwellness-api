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

- **Routers** (`app/api/routers/`) — faqat HTTP: parametrlarni qabul qilish, javob qaytarish
- **Services** (`app/services/`) — barcha biznes mantiq shu yerda
- **Models** (`app/models/`) — SQLAlchemy ORM, jadval strukturasi
- **Schemas** (`app/schemas/`) — Pydantic: HTTP kirish/chiqish validatsiyasi

## RBAC — Rollar

| Rol | Huquq |
|---|---|
| `super_admin` | Hamma narsani boshqaradi, markup belgilaydi, sanatoriyani tasdiqlaydi |
| `admin` | Faqat o'z sanatoriyasi, xonalari, mavjudligi, dasturlar, qo'shimcha o'rinlar |
| `agent` | Faqat o'z bronlarini ko'radi |
| `transfer_admin` | Transfer tariflari, avtoparki, buyurtmalari va moliyasi (platformada **bitta**) |
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
10. `booking_type = ROOM`, `status = PENDING`, `COMMIT`

**Bron holati to'lovga bog'liq.** Yangi bron doim `pending` — joy band
qilinadi, lekin stay to'lanmagan. `confirmed` ga faqat pul o'tkazadi: Uzum
Merchant `/confirm`, Checkout `COMPLETED`, yoki admin `confirm-cash`.
Shuning uchun sanatoriya adminsi uchun `confirmed` = "puli kelgan".

### Session booking

`booking_service.py::_create_session()` ichida:
1. `SELECT program` — `is_active` va `price`+`currency` to'ldirilgan bo'lishi shart
2. Sanatoriya `approved` ekanligini tekshir
3. `group_size_max` belgilangan bo'lsa, `guests <= group_size_max`
4. `check_out = check_out or check_in` (single-day session uchun OK)
5. `final_price = program.price × guests` (snapshot)
6. `booking_type = SESSION`, room_category_id = NULL, `COMMIT`

Cancel: room booking sanalardagi `units_available` ni qaytaradi; session booking faqat statusni `cancelled` qiladi.

### Bekor qilishda pul qaytishi

`app/services/cancellation_policy.py::refund_for()` — yagona joy. Shartlar
bronning o'zidan o'qiladi (`refundable`, `free_cancellation_days`,
`cancellation_penalty_percent|amount`), rate plan'dan emas: tarifni keyin
tahrirlash mavjud bronga ta'sir qilmaydi.

| Holat | Natija |
|---|---|
| `refundable = false` | Hech narsa qaytmaydi, hammasi jarima |
| `check_in − free_cancellation_days` gacha | To'liq qaytadi |
| Undan keyin | `cancellation_penalty_amount`, u yo'q bo'lsa `final_price × percent` ushlanadi |
| Shart umuman yo'q (rate plan'siz bron) | To'liq qaytadi |

Jarima to'langan summadan oshmaydi. Natija: `payments.refund_amount` (nechasi
qaytishi kerak) va `bookings.cancellation_penalty_snapshot` (nechasi
ushlab qolindi). Qaytariladigan puli bo'lgan payment `refund_pending` bo'ladi;
qaytariladigan puli yo'q payment `paid` bo'lib qoladi — sanatoriya uni saqlab
qoladi va moliya hisobotida qaytarim ko'rinmaydi.

## To'lov — Uzum Bank Merchant API

Yagona online provider — **Uzum Bank**. To'lov *ilovadan* boshlanadi: mijoz Uzum
Bank ilovasida UzWellness xizmatini tanlaydi, **bron raqamini** (`reservation_number`,
16 raqam) kiritadi, keyin Uzum bizning webhooklarni chaqiradi. Biz Uzumga hech
qachon so'rov yubormaymiz.

```
Uzum → POST /payments/uzum/check     → bron bor/to'lanmagan ekanini tasdiqlaymiz
Uzum → POST /payments/uzum/create    → Payment(status=pending) yaratamiz
Uzum → POST /payments/uzum/confirm   → Payment=paid, Booking=confirmed, email
Uzum → POST /payments/uzum/reverse   → pending→cancelled, paid→refunded
Uzum → POST /payments/uzum/status    → confirm timeout bo'lsa holatni so'raydi
```

| Uzum holati | `PaymentStatus` |
|---|---|
| `CREATED` | `pending` |
| `CONFIRMED` | `paid` |
| `REVERSED` | `cancelled` (to'lanmagan) / `refunded` (to'langandan keyin) |
| 30 daqiqa confirm yo'q | `failed` |

- **Auth:** HTTP Basic (`UZUM_MERCHANT_USERNAME` / `UZUM_MERCHANT_PASSWORD`).
  Sozlanmagan bo'lsa — hamma so'rov `10001` bilan rad etiladi (fail-closed).
- **Xatolar:** har qanday xato = HTTP `400` + `{"status":"FAILED","errorCode":"1000X"}`.
  Kodlar `app/integrations/uzum/errors.py` da.
- **Summa:** `amount` — **tiyin**, faqat **UZS**. Bron USD bo'lsa
  `ExchangeRateService` orqali UZS ga o'giriladi; mos kelmasa `10011`.
- **Idempotentlik:** `transId` bo'yicha partial unique index
  (`uq_payments_uzum_provider_payment_id`) — takroriy `/create` → `10010`.
- **Naqd** (`cash`) alohida qoladi: `POST /payments/initiate` + admin
  `POST /payments/{id}/confirm-cash`.

Uzum jamoasi uchun hujjat va Postman collection: `docs/uzum/`.

### Uzum Checkout — saytdagi karta to'lovi

Checkout **alohida mahsulot** (spetsifikatsiya 1.10.3): mijoz UzWellness
saytida karta bilan to'laydi. Bu yerda *biz* Uzumga so'rov yuboramiz, Uzum esa
natijani callback bilan qaytaradi. Merchant API bilan aralashtirmaslik kerak.

```
POST /payments/uzum-checkout/create            bron uchun to'lov ochish (auth)
GET  /payments/uzum-checkout/payments/{id}     holatni Uzumdan qayta o'qish
POST /payments/uzum-checkout/callback          moliyaviy natija (COMPLETE/REFUND/...)
POST /payments/uzum-checkout/event             biznes hodisa (FORM_CLOSED)
POST /payments/uzum-checkout/receipt           fiskal chek tayyor
```

Oqim:

```
POST /create → Uzum /api/v1/payment/register → {orderId, payment_url}
             → Payment(method='uzum_checkout', status=pending) saqlanadi
mijoz payment_url'ga yuboriladi va kartani kiritadi
Uzum → /callback  → biz Uzumga /payment/getOrderStatus yuboramiz
                  → COMPLETED bo'lsa Payment=paid, Booking=confirmed, email
```

- **Auth:** `X-Terminal-Id` + `X-API-Key` (Uzum beradi, har muhit uchun alohida).
  Sozlanmagan bo'lsa `/create` → `503`.
- **Summa:** `amount` — **tiyin**, faqat **UZS** (`currency: 860`). Bron USD
  bo'lsa `ExchangeRateService` orqali o'giriladi; kurs yo'q bo'lsa `503`.
- **`orderNumber`:** `{reservation_number}-{payment_id[:8]}` — har urinishda
  yangi (takroriy orderNumber → Uzum `3027`). Ochiq forma bo'lsa yangi order
  ochilmaydi, eskisi qayta ishlatiladi (ikki marta to'lash xavfi).
- **Fiskalizatsiya:** terminalda auto-fiscalization yoqilgan bo'lsa har
  `register` da `cart` kerak (aks holda `3045`) — bu Uzum tarafidagi sozlama,
  bizning `UZUM_CHECKOUT_AUTOFISCALIZATION` faqat cart yuborish/yubormaslikni
  boshqaradi. `spic`/`packageCode` tasnif katalogi bo'yicha tekshiriladi
  (`3055`), shuning uchun ular sozlamalarda:
  `10703999001000000` = "Услуги турагентств/туроператоров (бронирование,
  реализация турпакетов)", `1495084` = «услуга (раз)» — terminal MCC 4722 ga
  mos. (Mehmonxona varianti: `10204001001000000` + `1504157` «сутки».)
  Cart'da `receiptType` bo'lishi shart, item `title` ≤ 63 belgi.
- **Redirect URL'lar https bo'lishi shart** (`http://localhost` → `2000`).
  Register javobida to'lov sahifasi `result.paymentRedirectUrl` da keladi.
- **Xato kodlari:** javob har doim HTTP 200, haqiqiy holat — `errorCode`
  (`0` = OK). Non-zero → `UzumCheckoutApiError` → API `502`.

⚠️ **Checkout callback'lari imzolanmagan** (spetsifikatsiyada HMAC/signature
yo'q). Shuning uchun body'ga hech qachon ishonilmaydi: u faqat *qaysi order
o'zgargani*ni bildiradi, holat esa `POST /api/v1/payment/getOrderStatus` dan
olinadi. Tasdiqlab bo'lmagan callback `processed_at = NULL` bilan
`uzum_checkout_events` da qoladi va baribir `200 {}` qaytadi.

Parsing ataylab yumshoq: noma'lum maydonlar saqlanadi, yetishmagani `None`
bo'ladi, JSON buzilgan bo'lsa ham `200` qaytadi (qayta yuborish yordam
bermaydi) — bildirishnomani yo'qotmaslik uchun.

Test kartalar: HUMO `9860 0901 0121 9724` (10/26), UzCard `8600 3129 2957 7175`
(09/26), 3-DS kodi `777777`.

## Transfer — tarif, bron qo'shimchasi, moliya

Transferni **bitta** platforma operatori (`transfer_admin`) boshqaradi. Bitta
bo'lishi partial unique index bilan majburlanadi
(`uq_users_single_transfer_admin`); ikkinchisini yaratish → `409`
`{detail:{code:"transfer_admin_exists", existing_user_id}}`.

### Tarif — versiyalanadi, o'zgartirilmaydi

`transfer_tariffs` — append-only. "Tahrirlash" = joriy qatorni yopish
(`effective_to = now()`) + yangi ochiq qator qo'shish, **bitta tranzaksiyada**.
PATCH/DELETE yo'q. Har (route_from, route_to, vehicle_type) uchun `effective_to
IS NULL` bo'lgan faqat bitta qator bo'ladi — `uq_transfer_tariffs_current`.

Shu sababli bronning `applied_tariff_id` si doim mehmon to'lagan aniq narxga
ishora qiladi, tarif keyinchalik o'zgarsa ham.

`round_trip` narxi = to'g'ri yo'nalish tarifi + **teskari** yo'nalish tarifi.
Uchinchi o'lchov (direction) tarif jadvalida yo'q.

### Bron ichida transfer (bitta to'lov)

`POST /bookings` va `POST /bookings/room-offer` ixtiyoriy `transfer` blokini
qabul qiladi. **Mijoz hech qachon narx yubormaydi** — backend submit paytidagi
joriy tarifni topadi:

```
flush(booking) → attach_booking_transfer() → commit
                 ├─ tarifni yechadi (yo'q bo'lsa 422 no_tariff_for_route)
                 ├─ kerak bo'lsa bron valyutasiga o'giradi va snapshot qiladi
                 ├─ booking.final_price += transfer narxi
                 └─ TransferRequest(payment_state='included')
```

Hammasi bitta tranzaksiyada — tarif topilmasa bron ham yaratilmaydi.

| Holat | `payment_state` |
|---|---|
| Checkout ichida qo'shilgan | `included` (bron to'lovi bilan birga) |
| Brondan keyin `POST /transfers` | `unpaid` (alohida, offline hisob-kitob) |
| Operator to'lovni qabul qildi | `paid` |

Bron bekor qilinsa → bog'liq transferlar `cancelled` bo'ladi va moliyadan
chiqib ketadi.

### Komissiya

`users.transfer_commission_percent` — `transfer_admin` uchun majburiy (yo'q
bo'lsa `422`). Har transferga narxlash paytida **snapshot** qilinadi
(`commission_percent_snapshot`, `commission_amount_snapshot`), shuning uchun
foizni keyin o'zgartirish eski buyurtmalarga ta'sir qilmaydi.

Bu sanatoriya bilan bo'linishdan **alohida**: `GET /transfer-finance/summary`
o'z hisobini beradi (`net_payout = gross − commission`).

> ⚠️ `booking.final_price` transfer narxini ham o'z ichiga oladi, lekin
> `bookings.commission_snapshot` faqat xona/dastur qismidan hisoblanadi.
> Shuning uchun umumiy `/finance/summary` da `sanatorium_net_amount` transfer
> summasini ham ko'rsatadi. Sanatoriya hisob-kitobi uchun undan
> `/transfer-finance` gross'ini ayirish kerak.

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

transfer_locations ──→ transfer_tariffs (versiyalangan, append-only)
        │                      │
        └──────────────────────┴──→ transfer_requests ←── bookings
                                          ↑
                                  transfer_vehicles

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

# To'lov (Uzum Bank Merchant API + naqd)
POST      /payments/initiate            faqat naqd (cash) uchun
POST      /payments/{id}/confirm-cash   admin naqd to'lovni tasdiqlaydi
GET       /payments/uzum/order/{booking_id}   mehmonga ko'rsatiladigan order_id + UZS summa
POST      /payments/uzum/check|create|confirm|reverse|status   ← Uzum chaqiradi (Basic auth)

# Amenitlar (global katalog — super_admin)
GET/POST  /amenities
GET/PATCH/DELETE  /amenities/{id}

# Qo'shimcha o'rinlar (admin — o'z sanatoriyasi uchun)
GET/POST  /extra-beds?sanatorium_id=X
GET/PATCH/DELETE  /extra-beds/{id}

# Reviews
GET/POST  /sanatoriums/{id}/reviews
PATCH/DELETE  /reviews/{id}

# Transfer (transfer_admin + super_admin yozadi)
GET       /transfer-locations           public; ?is_active&kind&include_translations
POST/PATCH/DELETE  /transfer-locations[/{id}]
GET       /transfer-tariffs             tarix, ?route_from_id&route_to_id&vehicle_type&current_only
POST      /transfer-tariffs             yangi versiya (eskisini yopadi)
GET       /transfer-tariffs/current     public — checkout narxi (route + vehicle_type)
GET/POST/PATCH/DELETE  /transfer-vehicles[/{id}]
GET       /transfers                    ?status&payment_state&booking_id
POST      /transfers                    brondan keyin qo'shish → unpaid
PATCH     /transfers/{id}               rolga qarab: operator hammasini, mijoz faqat reys/kontakt
POST      /transfers/{id}/cancel
GET       /transfer-finance/summary|orders   ?date_from&date_to&currency
```

## Xatolar shartnomasi

Frontend `detail` ni **o'zgartirmasdan** mehmonga ko'rsatadi. Shuning uchun har
bir xabar to'liq gap bo'lishi va nima qilish kerakligini aytishi shart —
"Invalid" emas, "This rate must be booked at least 2 days before arrival".

Barcha javob shakli bir xil: `{"detail": "..."}` (422 da esa FastAPI'ning
`loc`/`msg` massivi).

| Holat | Qachon |
|---|---|
| `400` | So'rov mantiqan noto'g'ri (sana, narx, scope, FK topilmadi) |
| `401` | Token yo'q/eskirgan |
| `403` | Rol yoki egalik yetmaydi |
| `404` | Resurs yo'q **yoki** ko'rishga huquq yo'q (bron ro'yxati filtri) |
| `409` | Holat to'qnashuvi: band, allaqachon to'langan, dublikat |
| `422` | Pydantic validatsiyasi (`loc` bilan aniq maydon) |
| `429` | Rate limit |
| `502` | Uzum javob bermadi / rad etdi |
| `503` | Kurs yo'q, Checkout sozlanmagan, DB yo'q |

`app/api/error_handlers.py` — oxirgi himoya qatlami:

- **Har qanday tutilmagan xato** → `500` JSON + `reference <hex>`; log'da shu
  reference bilan traceback (`uzwellness.errors`). Plain-text 500 chiqmaydi.
- **`IntegrityError`** → sqlstate'ga qarab `409`/`400` + tushunarli xabar
  (`This code is already in use`). Ustun **qiymati** hech qachon javobga
  chiqmaydi, faqat log'da.
- **`OperationalError`** (DB yiqilgan) → `503`, retry taklifi bilan.
- **`RequestValidationError`** → javob o'zgarmaydi, lekin `uzwellness.validation`
  log'iga qaysi maydon yiqilgani yoziladi (qiymatsiz).

`UnhandledErrorMiddleware` **CORS'dan oldin** register qilinadi — aks holda
500 javobda `Access-Control-Allow-Origin` bo'lmaydi va brauzer xabarni
umuman ko'rsatmaydi.

Qulflash qoidasi: `room_availability` va `rate_plan_date_rules` qatorlari
birinchi yozuvda yaratiladi, shuning uchun ularga tegishdan oldin ota-qator
qulflanadi (`lock_rows(db, Room, [room_id])`) — bo'lmasa ikki barobar "Save"
bosilganda unique constraint buziladi.

## Test infratuzilmasi

```python
# conftest.py da tayyor fixture'lar:
customer_headers, admin_headers, super_admin_headers
db  # har test uchun yangi session, keyin reset_test_data() (DELETE, bola jadvallardan boshlab)
client  # ASGI test client, dependency override qilingan
```

## Ishlash qoidalari

### Code quality
Ish tugagandan oldin:
```bash
ruff check .
ruff format .
pytest  # yoki tegishli testlar
```

### Code review ustuvorligi
1. Security  2. Data integrity  3. Reliability  4. Correctness  5. Performance  6. Maintainability  7. Style

### Opportunity scanner
Ish davomida aloqasi yo'q yaxshilanishlarni (xavfsizlik, performance, soddalik) ko'rsangiz — alohida xabar bering, so'ralmasa implement qilmang.

### Qaror formati
Muhim qarorlar uchun: variantlar, trade-off'lar, tavsiya va sabab ko'rsating.

### Backend preferences
Python type hints, FastAPI best practices, dependency injection, explicit validation, proper error handling.

## Fayl qo'shish tartibi

Yangi entity uchun (masalan `Payment`):
1. `app/models/payment.py` — ORM model
2. `app/models/__init__.py` — export qo'sh
3. `app/schemas/payment.py` — Pydantic schemas
4. `app/services/payment_service.py` — biznes mantiq
5. `app/api/routers/payments.py` — HTTP endpoints
6. `app/api/__init__.py` — router ni include qil
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

## Deploy (VPS — systemd + unix socket + nginx)

Prodda app **Docker'da emas**: systemd service uvicorn'ni unix socket'da
ishga tushiradi, nginx esa o'sha socket'ga proxy qiladi. Postgres va redis
host'da allaqachon ishlaydi. (`docker-compose.yml` faqat lokal dev uchun.)

```bash
git pull
uv sync --frozen
uv run alembic upgrade head
sudo systemctl restart uzwellness   # unit nomi: uzwellness.service
journalctl -u uzwellness -f
```

### Infra config (nginx/systemd) — repo bilan sinxronlash

nginx va systemd fayllari VPS'da yashaydi, lekin git'dagi nusxasi
(`deploy/nginx/api.uzwellness.com`, `deploy/systemd/*.service|*.timer`)
haqiqiy manba hisoblanadi. **VPS'dagi faylni to'g'ridan-to'g'ri
tahrirlama** — avval shu repo'da o'zgartir, keyin serverga nusxala va
reload qil:

```bash
scp deploy/nginx/api.uzwellness.com root@vps:/etc/nginx/sites-available/
scp deploy/systemd/uzwellness*.service deploy/systemd/uzwellness*.timer root@vps:/etc/systemd/system/
ssh root@vps "nginx -t && systemctl reload nginx && systemctl daemon-reload && systemctl restart uzwellness"
```

Certbot'ning "managed by Certbot" izohli qatorlarini `certbot renew`
o'zi yangilab turadi — ularga qo'l tegizma, faqat faylning qolgan qismini
sinxron tut.

Hardened unit `User=uzwellness` bilan ishlaydi. **Birinchi o'rnatishdan
oldin** host'da (aks holda servis 217/USER bilan yiqiladi):

```bash
useradd --system --no-create-home --shell /usr/sbin/nologin uzwellness
chown -R uzwellness:www-data /var/www/uzwellness-api/uploads
```

`.env` `root:root 0600` qoladi — systemd uni root sifatida o'qiydi.

`tests/test_deployment_config.py` bu fayllarning invariantlarini tekshiradi
(unit nomi, socket yo'li, least-privilege, security header'lar).

### Rate limiting uchun majburiy nginx sozlamasi

Unix socket'da peer manzili **yo'q** — `request.client` `None` bo'ladi, ya'ni
`TRUSTED_PROXY_IPS` hech qachon mos kelmaydi. Shuning uchun mehmonning
manzili faqat nginx qo'yadigan header'dan olinadi:

```nginx
proxy_set_header X-Real-IP $remote_addr;
```

Busiz `_client_ip()` hammani bitta `"unknown"` bucket'iga soladi va o'nta
noto'g'ri parol butun saytning login'ini 10 daqiqaga bloklaydi.
`X-Forwarded-For` ham o'qiladi (o'ngdan chapga, `TRUSTED_PROXY_IPS` dagi
hop'lardan o'tib), lekin `X-Real-IP` aniqroq — uni mijoz to'ldira olmaydi.

`--forwarded-allow-ips=*` **ishlatilmasin**: u uvicorn'ga har qanday
`X-Forwarded-For` ga ishonishni aytadi va `request.client` ni o'sha
header'dan yozadi, ya'ni rate limit bucket'ini hujumchi o'zi tanlaydi.

### Uzum Checkout callback'lari

`/api/payments/uzum-checkout/{callback,event,receipt}` imzolanmagan (Uzum
spetsifikatsiyasida signature yo'q) va har chaqiruv bizni Uzumga qayta
so'rov yuborishga majbur qiladi. App tarafida IP bo'yicha rate limit bor,
lekin nginx darajasida Uzum manzillari uchun `allow`/`deny` qo'yish kerak.

### SSL

```bash
sudo certbot --nginx -d api.uzwellness.com
```

### Kunlik job (systemd timer)

Tugagan `confirmed` bronlarni `completed` ga o'tkazish cron emas, systemd
timer: `deploy/systemd/uzwellness-complete-bookings.{service,timer}`
(har kuni 03:00 Toshkent, `Persistent=true` — server o'chiq bo'lsa keyin
yetkazib oladi).

```bash
systemctl enable --now uzwellness-complete-bookings.timer
systemctl list-timers | grep uzwellness
```
