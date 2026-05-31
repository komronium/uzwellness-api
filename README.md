# UzWellness API

Backend for **uzwellness.com** — an aggregator for Uzbekistan sanatoriums and
wellness centers. Two product surfaces share one data model:

- **Sanatoriums** — medical resorts; the unit of sale is a **room-night** plus
  optional bundled treatment programs.
- **Wellness centers** — yoga studios, spa resorts, meditation centers,
  detox retreats; the unit of sale is a **program/session** (drop-in class,
  weekend retreat, etc.) with its own price.

**Stack:** FastAPI · PostgreSQL · Redis · SQLAlchemy 2 (async) · Alembic · JWT auth · uv

## Status

| Iteration | Scope                                                            | State    |
|-----------|------------------------------------------------------------------|----------|
| v0.1      | Auth + User + RBAC                                               | shipped  |
| v0.2      | Sanatorium CRUD + media                                          | shipped  |
| v0.3      | Rooms + availability + markup engine                             | shipped  |
| v0.4      | Booking flow (room) + extra beds + treatment programs            | shipped  |
| v0.5      | Reviews + seasonal pricing + Humson Buloq seed                   | shipped  |
| **v0.6**  | Sanatorium/Wellness split + session booking + wellness fields    | current  |

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for dep management
- Docker (for Postgres and Redis)

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Copy and edit env
cp .env.example .env
# Edit .env — set JWT_SECRET_KEY, INITIAL_SUPER_ADMIN_EMAIL/PASSWORD

# 3. Start Postgres
docker run -d --name uzwellness-pg \
  -e POSTGRES_USER=sanotour -e POSTGRES_PASSWORD=sanotour \
  -e POSTGRES_DB=sanotour -p 5432:5432 postgres:16-alpine
# Wait ~5s, then create the test database:
docker exec uzwellness-pg psql -U sanotour \
  -c "CREATE DATABASE sanotour_test;"

# 4. Apply migrations
uv run alembic upgrade head

# 5. Seed initial super_admin
uv run python -m scripts.seed

# 6. (Optional) Seed Humson Buloq with full price-list data
uv run python -m scripts.humson_buloq

# 7. Run dev server (port 8000 is often busy locally — use 8080)
uv run fastapi dev app/main.py --port 8080
```

API docs: http://127.0.0.1:8080/docs

## Authentication

JWT bearer tokens. **Get a token:**

```bash
curl -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@uzwellness.com","password":"Admin123!"}'
```

In Swagger UI: open `/docs`, click **Authorize**, paste the `access_token`
(no `Bearer ` prefix).

**Roles:** `super_admin` · `admin` · `agent` · `customer`

## Property model

A single `sanatoriums` table backs both product surfaces, discriminated by
`property_type`:

| Field                  | Sanatorium                                  | Wellness center                                            |
|------------------------|---------------------------------------------|------------------------------------------------------------|
| `property_type`        | `sanatorium`                                | `wellness`                                                 |
| `wellness_category`    | `null`                                      | `spa_resort` / `yoga_retreat` / `meditation_center` / `fitness_resort` / `beauty_spa` / `digital_detox` |
| Primary inventory      | `RoomCategory` rows (per-night pricing)     | `TreatmentProgram` rows (session/retreat pricing)          |
| Listing filter         | `region`, `treatment_focus`, `min_rating`   | `wellness_category`, `city`, `min_rating`                  |
| Booking type           | `room` (locks daily availability)           | `session` (`program.price × guests`)                       |

## Endpoints

### Health + auth

| Method | Path                       | Auth                         |
|--------|----------------------------|------------------------------|
| GET    | `/api/v1/health`           | —                            |
| GET    | `/api/v1/health/db`        | —                            |
| POST   | `/api/v1/auth/register`    | — (creates customer)         |
| POST   | `/api/v1/auth/login`       | —                            |
| POST   | `/api/v1/auth/refresh`     | — (refresh token in body)    |

### Users

| Method | Path                  | Auth        |
|--------|-----------------------|-------------|
| GET    | `/api/v1/users/me`    | any role    |
| GET    | `/api/v1/users`       | super_admin |
| GET    | `/api/v1/users/{id}`  | super_admin |
| PATCH  | `/api/v1/users/{id}`  | super_admin |

### Sanatoriums & Wellness centers

| Method | Path                                       | Auth                                | Notes                                                                                                                            |
|--------|--------------------------------------------|-------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| GET    | `/api/v1/sanatoriums`                      | optional                            | Filters: `property_type`, `wellness_category`, `city`, `region`, `status`, `stars`, `min_rating`, `q`, `amenity_ids`, `treatment_focus`, `sort`, `limit`, `offset` |
| GET    | `/api/v1/sanatoriums/{id}`                 | optional                            | Public sees only `approved`; admin sees own; super_admin sees all                                                                |
| POST   | `/api/v1/sanatoriums`                      | super_admin                         | Creates with `status=pending`                                                                                                    |
| PATCH  | `/api/v1/sanatoriums/{id}`                 | super_admin or owning admin         | Name change auto-regenerates slug                                                                                                |
| POST   | `/api/v1/sanatoriums/{id}/approve`         | super_admin                         | Flips status to `approved`                                                                                                       |
| POST   | `/api/v1/sanatoriums/{id}/images`          | super_admin or owning admin         | Multipart; JPEG/PNG/WebP up to 10 MB                                                                                             |

### Amenities (global catalog)

| Method | Path                          | Auth        |
|--------|-------------------------------|-------------|
| GET    | `/api/v1/amenities`           | —           |
| POST   | `/api/v1/amenities`           | super_admin |
| GET    | `/api/v1/amenities/{id}`      | —           |
| PATCH  | `/api/v1/amenities/{id}`      | super_admin |
| DELETE | `/api/v1/amenities/{id}`      | super_admin |

### Programs (treatment + wellness)

| Method | Path                                | Auth                |
|--------|-------------------------------------|---------------------|
| GET    | `/api/v1/programs?sanatorium_id=…`  | —                   |
| POST   | `/api/v1/programs`                  | admin / super_admin |
| GET    | `/api/v1/programs/{id}`             | —                   |
| PATCH  | `/api/v1/programs/{id}`             | admin / super_admin |
| DELETE | `/api/v1/programs/{id}`             | admin / super_admin |

A program has either `min_nights`/`max_nights` (sanatorium bundle) **or**
`price`+`currency`+`duration_minutes` (wellness session). Optional fields:
`instructor_name`, `instructor_bio`, `group_size_min/max`, `what_to_bring`,
amenity links.

### Rooms

| Method | Path                                                  | Auth                |
|--------|-------------------------------------------------------|---------------------|
| GET    | `/api/v1/rooms?sanatorium_id=…`                       | —                   |
| GET    | `/api/v1/rooms/search?check_in=…&check_out=…&guests=…`| —                   |
| POST   | `/api/v1/rooms`                                       | admin / super_admin |
| GET    | `/api/v1/rooms/{id}`                                  | —                   |
| PATCH  | `/api/v1/rooms/{id}`                                  | admin / super_admin |
| GET    | `/api/v1/rooms/{id}/availability`                     | —                   |
| POST   | `/api/v1/rooms/{id}/availability`                     | admin / super_admin |

### Extra beds

| Method | Path                                  | Auth                |
|--------|---------------------------------------|---------------------|
| GET    | `/api/v1/extra-beds?sanatorium_id=…`  | —                   |
| POST   | `/api/v1/extra-beds`                  | admin / super_admin |
| GET    | `/api/v1/extra-beds/{id}`             | —                   |
| PATCH  | `/api/v1/extra-beds/{id}`             | admin / super_admin |
| DELETE | `/api/v1/extra-beds/{id}`             | admin / super_admin |

### Bookings

| Method | Path                                    | Auth                | Notes                                                                            |
|--------|-----------------------------------------|---------------------|----------------------------------------------------------------------------------|
| POST   | `/api/v1/bookings`                      | any auth role       | Exactly one of `room_category_id` or `program_id` must be set.                   |
| GET    | `/api/v1/bookings`                      | any auth role       | Customer sees own; admin sees their sanatorium's; super_admin sees all.          |
| GET    | `/api/v1/bookings/{id}`                 | any auth role       | Subject to visibility rules                                                       |
| PATCH  | `/api/v1/bookings/{id}/cancel`          | owner / admin       | Room: restores per-date availability. Session: status flip only.                  |

### Reviews

| Method | Path                                              | Auth                  |
|--------|---------------------------------------------------|-----------------------|
| GET    | `/api/v1/sanatoriums/{id}/reviews`                | —                     |
| POST   | `/api/v1/sanatoriums/{id}/reviews`                | customer (booked)     |
| PATCH  | `/api/v1/reviews/{id}`                            | review author         |
| DELETE | `/api/v1/reviews/{id}`                            | author / super_admin  |

### Exchange rates

| Method | Path                                  | Auth        |
|--------|---------------------------------------|-------------|
| GET    | `/api/v1/exchange-rates`              | —           |
| POST   | `/api/v1/exchange-rates`              | super_admin |

## Pricing (rooms)

```
weekday  price = base_price          × (1 + markup/100) × (1 − discount/100)
weekend  price = base_price_weekend  × (1 + markup/100) × (1 − discount/100)
```

Friday and Saturday count as weekend. If the stay date falls inside a
`RoomPricePeriod`, its `base_price` / `base_price_weekend` / `discount_percent`
override the room defaults for that date.

```
booking.final_price = Σ(per-night price) + Σ(extra_bed.price_per_night × count × nights)
```

`final_price` is a snapshot — markup or discount changes after the booking
don't affect it. The same is true for `BookingExtraBed.price_per_night_snapshot`.

## Tests

```bash
uv run pytest
uv run pytest tests/test_booking_flow.py -v   # one file
```

## DevOps Shortcuts

```bash
make help
make install
make check
make up
make logs
make down
```

CI runs Ruff, compile, Alembic single-head validation, and the full test suite on
pushes to `main` and pull requests.

Tests use a separate database (`sanotour_test`) and reset the schema once per
session. See `tests/conftest.py` for fixtures (`customer_headers`,
`admin_headers`, `super_admin_headers`, `db`, `client`).

## Demo data

```bash
uv run python -m scripts.demo_data       # generic demo set
uv run python -m scripts.humson_buloq    # full Humson Buloq price-list seed
```

`humson_buloq.py` purges and re-creates: 1 sanatorium · 9 room categories ×
120 days availability · 4 treatment programs · 49 amenities · 2 extra-bed
configs · 1 seasonal price period (8 Sep – 30 Dec 2025).

Demo credentials (after `scripts.demo_data`):

```
super_admin: admin@uzwellness.com / Admin123!
admin:       charvak@uzwellness.com / Admin123!
customer:    ali@gmail.com / User123!
```

## Project layout

```
app/
  api/v1/routers/   # HTTP routers (thin: parse → call service → return)
  api/deps.py       # auth deps (HTTPBearer, get_current_user, require_roles)
  core/             # config, database, security (bcrypt, JWT), pricing
  models/           # SQLAlchemy models
  schemas/          # Pydantic schemas
  services/         # business logic
alembic/            # migrations
scripts/            # seed.py, demo_data.py, humson_buloq.py
tests/              # pytest fixtures + tests
docs/               # TZ.md, ROADMAP.md, frontend_features.html
```

## Tooling

```bash
uv run alembic revision --autogenerate -m "..."   # new migration
uv run alembic upgrade head                       # apply
uv run alembic downgrade -1                       # roll back one
uv run ruff check .                               # lint
uv run ruff format .                              # format
```

## Frontend handoff

For a feature-by-feature breakdown intended for the frontend team, see
`docs/frontend_features.html` — it covers the property model, listing/detail
endpoints with sample JSON, the room vs session booking flow, and the wellness
detail fields.
