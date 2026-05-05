# SanaTour — Consolidated Technical Specification

> **This is a working synthesis of two source TZ documents.**
> - Original sources: [`refs/TZ_sanatour.md`](refs/TZ_sanatour.md) (uz, v1) · [`refs/TZ_uzsanatorium.md`](refs/TZ_uzsanatorium.md) (ru, v2)
> - **Status:** core scope agreed; some strategic questions still open (see §3).
> - This document evolves as decisions are made. The two source TZs in `refs/` are frozen.

---

## 1. Project at a glance

**SanaTour / UzSanatorium** — an aggregator platform that brings every Uzbekistan sanatorium onto a single site, with online booking for rooms, transport, and tickets.

**Business model:** sanatoriums submit a base price → the platform's super_admin adds a **markup (percentage)** → the customer sees the final price. This is the central revenue mechanism, present in both source TZs.

**Target market:** Uzbekistan — both **local users and foreign tourists** (confirmed). UI defaults to USD pricing; UZS prices shown alongside.

---

## 2. Core scope (both TZs agree)

### 2.1 User roles

| Role code | Description | Notes |
|---|---|---|
| `super_admin` | Platform owner. Approves sanatoriums, sets markup, manages users, finance, statistics. | Single role, no "manager" tier in MVP |
| `admin` | **Sanatorium** admin. Manages own sanatorium profile, rooms, prices, bookings. | Linked to one sanatorium via FK |
| `agent` | B2B corporate user — books on behalf of a company, sees wholesale prices. | Optional in MVP, deferred to a later iteration |
| `customer` | B2C end-user (tourist). Searches, books, pays, leaves reviews. | Default role on public registration |

**Future role additions (post-MVP):**
- `platform_manager` — limited platform admin (can adjust markup but not delete sanatoriums)
- `sanatorium_staff` — read-only staff under a sanatorium admin

### 2.2 Modules

| Module | Description | Phase |
|---|---|---|
| **Sanatorium catalog** | Listing, filters, detail page, map, reviews | ✅ MVP |
| **Booking** | Date selection, guest info, price calculation, voucher | ✅ MVP |
| **Markup engine** | Sanatorium base price → super_admin markup → final price | ✅ MVP |
| **Auth + RBAC** | Email/password, JWT + refresh, role-based access | ✅ MVP |
| **Multi-language** | EN / RU / UZ | ✅ MVP |
| **Multi-currency** | USD primary + UZS (EUR/RUB later) | ✅ MVP |
| **Payments** | Payme, Click, Stripe | 🟡 Phase 2 |
| **Email + SMS** | Booking confirmations, voucher PDF | 🟡 Phase 2 |
| **Sanatorium admin panel** | Profile, rooms, prices, bookings UI | 🟡 Phase 2 |
| **Rent Car** | Vehicle rental (with optional driver) | 🟢 Phase 3 |
| **Train (UTY)** | Railway tickets via Uzbekistan Railways | 🟢 Phase 3 |
| **Flights (Sabre/Amadeus)** | Air tickets via GDS | 🔵 Phase 4 |
| **Reviews + Promo** | Reviews, promo codes, special offers | 🔵 Phase 4 |

### 2.3 Technology stack (chosen)

| Layer | Choice | Status |
|---|---|---|
| Backend | **FastAPI + Python 3.13** | ✅ chosen (deviates from TZ recommendation of NestJS) |
| ORM | SQLAlchemy 2.0 (async) + Alembic | ✅ |
| Database | PostgreSQL 16 (Docker) | ✅ |
| Cache | Redis 7 (Docker) | ✅ |
| Package manager | `uv` | ✅ |
| Frontend | Next.js 14+ (App Router) + Tailwind + shadcn/ui | 🔜 separate project |
| File storage | S3 or Cloudflare R2 | 🔜 |
| Email | SendGrid | 🔜 |
| SMS | Twilio (international) or Eskiz/Playmobile (local) | 🔜 |
| Maps | Google Maps or Yandex | 🔜 |

### 2.4 Non-functional requirements

- **Security:** JWT + refresh, RBAC per endpoint, bcrypt password hashing, encrypted passport data, 2FA on admin panels
- **Compliance:** GDPR + Uzbekistan PDP law (personal data protection)
- **Performance:** API response < 500ms under 1000 concurrent users, Redis caching
- **SEO:** SSR (frontend), JSON-LD, sitemap, OG tags
- **Audit log:** every admin action recorded
- **Refund:** per-channel refund flow

---

## 3. Open questions (decisions pending)

Some answered below; others to be decided as we hit them.

| # | Question | TZ#1 | TZ#2 | **Decision** |
|---|---|---|---|---|
| 1 | Target market | Local + foreign | Foreign only | **Local + foreign** ✅ |
| 2 | Auth method | SMS OTP + Google | Email + Firebase/Supabase | **Email + password (MVP)**, Google OAuth + SMS OTP later |
| 3 | Transfer module | Separate | Inside Rent Car | **Inside Rent Car** (driver option), separate module later if needed |
| 4 | Sanatorium Staff role | No | Yes (read-only) | Not in MVP |
| 5 | Platform Manager role | No | Yes | Not in MVP, super_admin alone is enough |
| 6 | Cash payment | Yes | No | Not in MVP, "pay on arrival" can come later |
| 7 | Apple/Google Pay | Yes | No | Comes free via Stripe later |
| 8 | Currencies | UZS+USD+EUR | USD+UZS+EUR+RUB | **UZS + USD only** (MVP), others later |
| 9 | Markup type | — | percentage or fixed | **Percentage** ✅ |
| 10 | PWA / Dark mode | Yes | No | Not in MVP |
| 11 | Loyalty program | Future | Nice-to-have | Post-MVP |

---

## 4. MVP — minimum complete vertical slice

**Goal:** customer searches → finds → books → pays → receives voucher. Super_admin approves sanatorium and sets markup. Sanatorium admin manages own rooms.

### 4.1 Database models (MVP)

| Model | Purpose |
|---|---|
| `User` | role, email, password_hash, profile, phone |
| `Sanatorium` | name, address, geo (lat/lng), images, status (pending/approved/rejected), `admin_user_id` FK |
| `RoomCategory` | sanatorium FK, name, capacity, `base_price`, `base_currency`, `markup_percent`, images |
| `RoomAvailability` | room_category FK, date, units_available, units_total |
| `Booking` | user FK, room_category FK, check_in, check_out, guests, status, final_price, currency |
| `Payment` | booking FK, channel (payme/click/stripe), status, transaction_id, amount |
| `ExchangeRate` | currency_pair, rate, valid_from |
| `Review` | user FK, sanatorium FK, rating, text *(post-MVP)* |

### 4.2 API endpoints (MVP)

```
# Auth
POST   /api/v1/auth/register             public
POST   /api/v1/auth/login                public
POST   /api/v1/auth/refresh              public
GET    /api/v1/auth/me                   any authenticated

# Users (super_admin)
GET    /api/v1/users                     super_admin
PATCH  /api/v1/users/{id}                super_admin
DELETE /api/v1/users/{id}                super_admin

# Sanatoriums
GET    /api/v1/sanatoriums               public (filter, search, paginate)
GET    /api/v1/sanatoriums/{id}          public
POST   /api/v1/sanatoriums               super_admin
PATCH  /api/v1/sanatoriums/{id}          super_admin or owning admin
POST   /api/v1/sanatoriums/{id}/approve  super_admin

# Rooms
GET    /api/v1/rooms?sanatorium_id=      public
POST   /api/v1/rooms                     admin (own sanatorium)
PATCH  /api/v1/rooms/{id}                admin (base price) or super_admin (markup)
GET    /api/v1/rooms/{id}/availability   public

# Bookings
POST   /api/v1/bookings                  customer or agent
GET    /api/v1/bookings                  filtered by role
GET    /api/v1/bookings/{id}             owner or super_admin
PATCH  /api/v1/bookings/{id}/cancel      owner or super_admin

# Payments
POST   /api/v1/payments/initiate         customer or agent
POST   /api/v1/payments/webhook/{provider} system (verified signature)

# Exchange rates (admin-managed for MVP)
GET    /api/v1/exchange-rates            public
PATCH  /api/v1/exchange-rates            super_admin
```

### 4.3 Markup engine

Sanatorium provides `base_price` in either UZS or USD. Super_admin sets `markup_percent` per room category.

```
final_price = base_price * (1 + markup_percent / 100)
```

For displaying in another currency, convert using `ExchangeRate` table (manually maintained for MVP, automated against cbu.uz API later).

**Example:**
- Sanatorium base: 500,000 UZS / night
- Markup: 15%
- Final: 575,000 UZS / night → ≈ $46 USD (via rate table)

### 4.4 Out of MVP scope

Flights, trains, transfer, B2B agent, reviews, promo codes, push notifications, AI recommendations, virtual tour, loyalty.

---

## 5. Roadmap (high level)

| Iteration | Scope | Estimated effort |
|---|---|---|
| **0.1** | Auth + User + RBAC | ~1 week |
| **0.2** | Sanatorium CRUD + media | ~1.5 weeks |
| **0.3** | Room category + availability + markup engine | ~1.5 weeks |
| **0.4** | Booking flow (no payment yet) | ~1 week |
| **0.5** | Payme + Click sandbox integration | ~2 weeks |
| **0.6** | Email/SMS notifications + voucher PDF | ~1 week |
| **MVP** | Frontend wiring + smoke tests + soft launch | ~1-2 weeks |

> Backend is the critical path. Frontend (Next.js) can start in parallel from 0.1 onward (auth UI), then 0.2 (listing), and so on.

> Detailed 28-day plan: see [`ROADMAP.md`](ROADMAP.md).

---

## 6. Documentation structure

```
docs/
├── TZ.md                         ← this file (working spec)
├── ROADMAP.md                    ← 28-day execution plan
└── refs/
    ├── TZ_sanatour.md            ← TZ #1 (Uzbek, original)
    └── TZ_uzsanatorium.md        ← TZ #2 (Russian, original)
```

Future additions as the project grows:
- `docs/architecture.md` — architecture decision records (ADRs)
- `docs/db_schema.md` — generated DB schema diagram
- `docs/api.md` — OpenAPI-generated endpoint reference
