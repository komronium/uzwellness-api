# 28-Day Roadmap — SanaTour Backend

> Goal: by end of Day 28, ship a working booking system (no payments yet) on GitHub with versioned tags v0.1 → v0.4.
> Assumes ~3-4 productive hours/day. Slip 1-2 days per week is normal — that's why each week ends with a buffer day for cleanup, tests, and the GitHub tag.

## At-a-glance

| Week | Iteration | Deliverable | GitHub tag |
|---|---|---|---|
| **W1 (D1-7)** | 0.1 | Auth + User + RBAC | `v0.1.0` |
| **W2 (D8-14)** | 0.2 | Sanatorium CRUD + media | `v0.2.0` |
| **W3 (D15-21)** | 0.3 | Rooms + availability + markup engine | `v0.3.0` |
| **W4 (D22-28)** | 0.4 | Booking flow (no payment) | `v0.4.0` |

## GitHub strategy

- **Day 1 (today):** initial commit + push to a **private** repo. Skeleton + docs included.
- **Every working day:** small commits, push at end of session. Don't batch.
- **End of each week:** annotated tag for the iteration milestone.
- **Branching:** work directly on `main` for MVP solo development. Open PRs for self-review only when the change spans 2+ days, or when a second contributor joins.
- **Repo visibility:** keep **private** until at least v0.3 (markup engine). Public earlier risks copycats before the differentiator ships.

---

## Week 1 — Auth + User + RBAC (Iteration 0.1)

| Day | Tasks | Files affected |
|---|---|---|
| **D1** | • `git init` + first commit (skeleton, docs, plan)<br>• Create private GitHub repo, push<br>• `User` model (id, email, password_hash, role enum, full_name, phone, created_at)<br>• Generate first alembic migration | `app/models/user.py`, `alembic/versions/...` |
| **D2** | • `Role` enum: `super_admin`, `admin`, `agent`, `customer`<br>• Password hashing utilities (bcrypt) — extend `app/core/security.py`<br>• JWT encode/decode (access + refresh)<br>• Pydantic schemas: `UserCreate`, `UserRead`, `Token` | `app/core/security.py`, `app/schemas/user.py`, `app/schemas/auth.py` |
| **D3** | • `POST /api/v1/auth/register` (default role = `customer`)<br>• `POST /api/v1/auth/login` (JWT + refresh)<br>• `POST /api/v1/auth/refresh` | `app/api/v1/routers/auth.py`, `app/services/user_service.py` |
| **D4** | • `get_current_user` dependency (JWT validation)<br>• `require_roles(...)` dependency factory for RBAC<br>• `GET /api/v1/auth/me` | `app/api/deps.py`, `app/api/v1/routers/auth.py` |
| **D5** | • `GET /api/v1/users` (super_admin only)<br>• `PATCH /api/v1/users/{id}` (role change, deactivate)<br>• Seed script: create initial super_admin from env vars | `app/api/v1/routers/users.py`, `scripts/seed.py` |
| **D6** | • Pytest fixtures: test DB, async client, authed user fixtures<br>• Tests: register, login, refresh, /me, RBAC denial cases | `tests/conftest.py`, `tests/test_auth.py`, `tests/test_users.py` |
| **D7** | • Buffer: any leftover<br>• `README.md` with setup instructions<br>• Commit, push, **tag `v0.1.0`** | `README.md` |

**End of W1 status:** registration & login work. Roles enforced. Super_admin seeded.

---

## Week 2 — Sanatorium catalog (Iteration 0.2)

| Day | Tasks | Files affected |
|---|---|---|
| **D8** | • `Sanatorium` model: name, slug, description (JSONB for translations: `{"en":..., "ru":..., "uz":...}`), city, address, lat, lng, stars, status enum (pending/approved/rejected), `admin_user_id` FK<br>• `SanatoriumImage` model (FK + URL + order)<br>• Migration | `app/models/sanatorium.py` |
| **D9** | • Pydantic schemas (translations as nested object)<br>• `POST /api/v1/sanatoriums` (super_admin)<br>• `PATCH /api/v1/sanatoriums/{id}` (super_admin or owning admin)<br>• `POST /api/v1/sanatoriums/{id}/approve` (super_admin) | `app/schemas/sanatorium.py`, `app/api/v1/routers/sanatoriums.py` |
| **D10** | • `GET /api/v1/sanatoriums` — listing (filter by city, status, stars; pagination via `limit`/`offset`)<br>• `GET /api/v1/sanatoriums/{id}` — detail<br>• Public sees only `status=approved`; admin sees own; super_admin sees all | `app/services/sanatorium_service.py` |
| **D11** | • Image upload endpoint: `POST /api/v1/sanatoriums/{id}/images`<br>• Local storage for now (`uploads/sanatoriums/{id}/`), S3 abstraction interface so it's swappable later<br>• Multipart form, file size limit, MIME validation | `app/services/storage.py`, `app/api/v1/routers/sanatoriums.py` |
| **D12** | • Search: full-text on `name` (Postgres `pg_trgm` extension or `ILIKE` for MVP)<br>• Sort: by name, stars, created_at<br>• Combine with filter | `app/services/sanatorium_service.py` |
| **D13** | • Tests: CRUD by role, listing filters, image upload, approval flow<br>• Test data factory | `tests/test_sanatoriums.py`, `tests/factories.py` |
| **D14** | • Buffer + cleanup<br>• Update README<br>• Commit, push, **tag `v0.2.0`** | |

**End of W2 status:** sanatoriums can be created, approved, listed, searched. Images upload locally.

---

## Week 3 — Rooms + Availability + Markup (Iteration 0.3)

| Day | Tasks | Files affected |
|---|---|---|
| **D15** | • `RoomCategory` model: sanatorium FK, name (translatable), capacity (int), `base_price` (Decimal), `base_currency` (UZS/USD), `markup_percent` (Decimal, default 0), `min_nights`, images<br>• `ExchangeRate` model: pair (e.g. `USD_UZS`), rate (Decimal), valid_from<br>• Migrations | `app/models/room.py`, `app/models/exchange_rate.py` |
| **D16** | • Room CRUD endpoints:<br>  - `POST /api/v1/rooms` (admin only — own sanatorium)<br>  - `PATCH /api/v1/rooms/{id}` (admin sets base_price; super_admin sets markup_percent)<br>  - `GET /api/v1/rooms?sanatorium_id=` (public, only approved sanatoriums) | `app/api/v1/routers/rooms.py` |
| **D17** | • Markup calculation in service layer: `final_price = base_price * (1 + markup_percent / 100)`<br>• Currency conversion utility using `ExchangeRate`<br>• `RoomRead` schema returns: `base_price`, `markup_percent`, `final_price`, `final_price_uzs`, `final_price_usd` | `app/services/pricing.py`, `app/schemas/room.py` |
| **D18** | • `RoomAvailability` model: room_category FK, date, units_available, units_total<br>• Bulk-create availability for date range (admin endpoint)<br>• `GET /api/v1/rooms/{id}/availability?from=...&to=...` | `app/models/availability.py`, `app/api/v1/routers/rooms.py` |
| **D19** | • Public room search: `GET /api/v1/rooms/search?check_in=...&check_out=...&guests=N` — returns rooms with full availability across the date range<br>• Logic: room is available iff `min(units_available) >= 1` for every date in range and capacity ≥ guests | `app/services/room_search.py` |
| **D20** | • `PATCH /api/v1/exchange-rates` (super_admin)<br>• `GET /api/v1/exchange-rates` (public)<br>• Tests: pricing math, RBAC on markup/base_price split, availability search, exchange rate resolution | `tests/test_pricing.py`, `tests/test_availability.py` |
| **D21** | • Buffer + cleanup<br>• Document markup logic in `docs/architecture.md` (first ADR)<br>• Commit, push, **tag `v0.3.0`** | `docs/architecture.md` |

**End of W3 status:** rooms exist, availability tracked, prices computed with markup, currency conversion works.

---

## Week 4 — Booking flow (Iteration 0.4)

| Day | Tasks | Files affected |
|---|---|---|
| **D22** | • `Booking` model: id, code (short random), user FK, room_category FK, check_in, check_out, guests, status enum (`pending`/`confirmed`/`cancelled`/`completed`), `final_price`, `currency`, `created_at`<br>• Migration | `app/models/booking.py` |
| **D23** | • `POST /api/v1/bookings` — atomic transaction:<br>  1. Validate dates (future, check_out > check_in, ≥ min_nights)<br>  2. Check capacity ≥ guests<br>  3. Lock room availability rows (`SELECT ... FOR UPDATE`)<br>  4. Verify all dates have `units_available ≥ 1`<br>  5. Decrement availability for each date<br>  6. Freeze final_price (snapshot of current markup logic)<br>  7. Insert booking with `status=pending` | `app/services/booking_service.py`, `app/api/v1/routers/bookings.py` |
| **D24** | • `GET /api/v1/bookings` — role-filtered:<br>  - customer/agent: own bookings<br>  - admin: bookings against their sanatorium<br>  - super_admin: all<br>• `GET /api/v1/bookings/{id}` — same access rules | `app/services/booking_service.py` |
| **D25** | • `PATCH /api/v1/bookings/{id}/cancel` — atomic:<br>  1. Verify ownership/role<br>  2. Verify status is cancellable<br>  3. Restore availability rows<br>  4. Set status=cancelled<br>• Cancellation rules: customer cancels their own; super_admin cancels any | `app/services/booking_service.py` |
| **D26** | • Notification stub: `Notification` model (booking FK, type, channel, status), insert rows on booking events but don't send yet<br>• Status auto-confirm for MVP (no payment) — add note in code that real flow will require payment success | `app/models/notification.py`, `app/services/notification_stub.py` |
| **D27** | • End-to-end integration test: register customer → search rooms → book → cancel → re-book<br>• Concurrency test: two simultaneous bookings on the last unit (verify locking) | `tests/test_booking_flow.py` |
| **D28** | • Documentation pass: update `docs/TZ.md` (mark MVP-0.4 done), update `README.md` with API docs link<br>• Commit, push, **tag `v0.4.0`**<br>• Brief retrospective: what slipped, what next | |

**End of W4 status:** complete booking lifecycle works without payment. Customer can search, book, cancel; admin sees their bookings; super_admin oversees all.

---

## After Day 28 — what's next

The next 4 weeks (Days 29-56) cover Iterations 0.5 (payments), 0.6 (notifications/voucher PDF), and frontend wiring. Don't plan that in detail yet — adjust based on Week 4 retrospective.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Solo dev burnout | Strict daily scope; buffer day each week; skip nice-to-haves |
| Scope creep from TZs | Refer to §3 of `TZ.md` for what's deferred; resist adding |
| Auth bugs late-found | Heavy unit tests in W1; integration test in D27 catches regressions |
| Migration breakage from rebases | One migration per day max; review before applying |
| Locking bugs in booking | D27 concurrency test; review SQL with `EXPLAIN` |

## Daily routine (suggested)

1. **Start (5 min):** read previous day's commit, glance at today's row in this table
2. **Code (~3 hours):** focused work on the day's tasks
3. **Test (~30 min):** run pytest, verify endpoints in `/docs`
4. **Commit & push (~10 min):** small descriptive commits
5. **Note (~5 min):** if anything slipped or surfaced, add to `docs/NOTES.md`

## Tools assumed

- `uv run fastapi dev app/main.py --port 8080` — dev server (port 8000 is occupied locally)
- `uv run alembic revision --autogenerate -m "..."` — generate migrations
- `uv run alembic upgrade head` — apply
- `uv run pytest` — tests
- `docker compose up -d` — postgres + redis
